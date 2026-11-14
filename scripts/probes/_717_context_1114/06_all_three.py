#!/usr/bin/env python3
"""#717 (2026-11-14, the build of his signed checks) — scorecard of all three signed checks (1d + A2(10) + lower line at the SIGNED line 0.2123, strict), using the
context card's own harness (scripts/probes/_717_context_1114/02_score.py's score(), exec'd like 03_posthoc.py does, its
file writes redirected to a temp dir; nothing in this directory is rewritten). The 36 grades of the first three sheets (ctx.load asserts 36; the fixture
holds 48 now — the 12 of the fourth sheet are filtered out, as ctx.load's sheet keys cover only the first three).
Lower line: fires = /Users/alvinfung/apollo_data/bv1_lowline_1114/fires_lowline.parquet (V3, LS30, nbars, computed by
01_capture.py); scorecard / High rows = PRODUCTION breakout_v1.context_gates on the 200-bar fixture windows.
Bridge: the 1d and 1d + A2(10) rows must reproduce 03_posthoc.out (466 / 380 / 26 and 449 / 366 / 26) and the 0.212 pool
_717_lowline_1114/03_sheet.out (114,824 fires after the lower line). Era A only; research, the rules are in breakout_v1.

    python3 scripts/probes/_717_context_1114/06_all_three.py > scripts/probes/_717_context_1114/06_all_three.out
"""
import io, contextlib, os, sys, tempfile
import numpy as np, pandas as pd
WT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
SCR = tempfile.mkdtemp()
CX = WT + '/scripts/probes/_717_context_1114'
sys.path.insert(0, WT); sys.path.insert(0, CX); sys.path.insert(0, WT + '/tests/fixtures')
import breakout_list_grades as BLG  # noqa
import ctx  # noqa
keys = set("scripts/probes/" + k for k in ctx.SHEET_KEYS)
ctx.MODEL_PICK_GRADES = [g for g in BLG.MODEL_PICK_GRADES if g.sheet in keys]
print("grades kept for the harness:", len(ctx.MODEL_PICK_GRADES))
from agents.market_intelligence import breakout_v1 as bv  # noqa
from agents.market_intelligence import consolidation_breakout as cb  # noqa
from datetime import date, timedelta  # noqa

src = open(CX + '/02_score.py').read()
src = src.replace('os.path.join(HERE, "02_drops.tsv")', repr(SCR + '/02_drops_rerun.tsv')).replace('os.path.join(HERE, "stack.txt")', repr(SCR + '/stack_rerun.txt'))
sys.argv = [sys.argv[0]]
buf = io.StringIO()
G = {"__name__": "s", "__file__": CX + '/02_score.py'}
os.chdir(CX)
with contextlib.redirect_stdout(buf):
    exec(compile(src, CX + '/02_score.py', 'exec'), G)
f, sc, hi, gr, NO, OKG, COND = (G[k] for k in ("f", "sc", "hi", "gr", "NO", "OKG", "COND"))
score, ONE_D, sized, FALL, WX, HDR = (G[k] for k in ("score", "ONE_D", "sized", "FALL", "WX", "HDR"))
A2_10, T, _ = sized("ret126", "min", FALL(10), 0.0)
print("A2(10) threshold T =", T)


def bars_of(W):
    ok = np.isfinite(W[3])
    n = int(ok.sum())
    ds = [date(2000, 1, 3) + timedelta(days=i) for i in range(n)]
    return cb.daily_bars_from_arrays(ds, *[list(W[j][ok]) for j in range(4)], [1.0] * n), n - 1


def prod(d):
    """production context_gates on each row's 200-bar fixture window -> (pass1, pass2, pass3, v3, slope, bars)."""
    out = []
    for w in d.w.to_numpy():
        b, D = bars_of(WX[w])
        adr = bv.adr20_at((b.h - b.l) / b.c, D)
        g = bv.context_gates(b, D, adr20=adr)
        v = g["lower_line"]["value"]
        out.append((g["sma50_falling_under"]["pass"], g["downtrend_6m"]["pass"], g["lower_line"]["pass"], v["v3"], v["slope30"], v["bars"]))
    return pd.DataFrame(out, index=d.index, columns=["p1", "p2", "p3", "V3p", "LSp", "nbp"])


for nm, d in (("scorecard", sc), ("High", hi)):
    p = prod(d)
    d[["p1", "p2", "p3", "V3p", "LSp", "nbp"]] = p
    r1 = ONE_D(d).to_numpy(); r2 = A2_10(d).to_numpy()
    print(f"{nm}: production vs research columns — 1d agree {int((p.p1.to_numpy() == r1).sum())}/{len(d)}, A2(10) agree {int((p.p2.to_numpy() == r2).sum())}/{len(d)}")
    d["LL"] = ~d.p3.astype(bool)

m = pd.read_parquet("/Users/alvinfung/apollo_data/bv1_lowline_1114/fires_lowline.parquet")
assert (m.index == f.index).all()
for line in (0.212, 0.2123):
    f["LL"] = ((m.nbars >= 189) & (m.V3 > line) & (m.LS30 <= 0)).to_numpy()
    for d in (gr, NO, OKG, COND):
        d["LL"] = f.LL.to_numpy()[d.w.to_numpy()]
    if line == 0.212:
        sc_ll, hi_ll = sc.LL.copy(), hi.LL.copy()
        V, L, n = sc.V3p.astype(float), sc.LSp.astype(float), sc.nbp
        sc["LL"] = ((n >= 189) & (V > 0.212) & (L <= 0)).to_numpy()
        V, L, n = hi.V3p.astype(float), hi.LSp.astype(float), hi.nbp
        hi["LL"] = ((n >= 189) & (V > 0.212) & (L <= 0)).to_numpy()
    else:
        sc["LL"], hi["LL"] = sc_ll, hi_ll
    f1 = f[ONE_D(f)]; pool = f1[A2_10(f1)]
    print(f"\n== V3 line {line} ({'research ll.py' if line == 0.212 else 'SIGNED, strict'}): fires {len(f):,} -> 1d {len(f1):,} -> +A2(10) {len(pool):,} -> + lower line {int((~pool.LL).sum()):,}")
    print(HDR)
    G["DROPS"].clear()
    score("1d", ONE_D)
    score("1d + A2(10)", lambda d: ONE_D(d) & A2_10(d))
    score(f"1d + A2(10) + lower line {line}", lambda d: ONE_D(d) & A2_10(d) & ~d.LL)
    score(f"lower line {line} alone", lambda d: ~d.LL)
    x = pd.DataFrame(G["DROPS"], columns=["check", "set", "eid", "ticker", "E", "tier", "big"])
    a = x[x.check == "1d + A2(10)"].eid; y = x[(x.check == f"1d + A2(10) + lower line {line}") & ~x.eid.isin(a)]
    print("fired buys lost beyond 1d + A2(10):", len(y), "; ".join(f"{r.ticker} {r.E} ({r.tier}{', BIG' if r.big else ''})" for r in y.itertuples()))
