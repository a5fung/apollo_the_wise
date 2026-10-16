"""Supplementary verifier checks (read-only): positive depth engagement from the LIVE walker's inputs,
the depth stop's effect on outcomes (ADR20 withheld), and the exploratory registration rule re-applied
to run_rows.tsv with an exact sign-flip. Reuses verify_indep's own loader (not recut.py)."""
import contextlib
import importlib.util
import io
import itertools
from collections import defaultdict
from datetime import date

P = "/Users/alvinfung/apollo_the_wise/scripts/probes/_runner_recut_1017"
spec = importlib.util.spec_from_file_location("vi", f"{P}/verify/verify_indep.py")
vi = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(vi)

from agents.market_intelligence.broker.exit_logic import depth_stop_price  # noqa: E402

# 1. SGML example stop, recomputed with the live pure function
print("SGML 04-22 depth stop from line 18.3760 / ADR 0.1064 / floor 15.85:",
      depth_stop_price(line=18.3760, hard_stop=14.75, entry_price=15.85, breakeven_active=True, adr20_pct=0.1064))

# 2. the depth stop's effect: same live walker, ADR20 withheld (rests at the floor) vs the real ADR20
diff, adr_changes = 0, []
for tr in vi.trades:
    k = (tr["t"], tr["d"].isoformat())
    real = vi.ctrl[k]
    tr2 = dict(tr, adr=None)
    noadr = vi.live(tr2)
    if (real[1] is None) != (noadr[1] is None) or (real[1] is not None and abs(real[1] - noadr[1]) > 0.005):
        diff += 1
        adr_changes.append((k, None if real[1] is None else round(real[1], 3), None if noadr[1] is None else round(noadr[1], 3)))
print(f"control with ADR20 withheld (depth stop at the floor) differs from the real control on {diff} of {len(vi.trades)} trades")
print("  first 8:", adr_changes[:8])
tot_real = sum(v[1] for v in vi.ctrl.values() if v[1] is not None)
print(f"  total R real ADR20 {tot_real:+.2f}")

# 3. close-below sales priced at the next open vs the deciding close (own clone exits)
cb = [(k, v["exit"]) for k, v in vi.mine_ctrl.items() if v["exit"] and v["exit"][1] == "close_below@next_open"]
print(f"close-below sales in own clone: {len(cb)}; next open != deciding close on {sum(1 for _, e in cb if abs(e[2] - e[3]) > 1e-9)}")
above = [(k, v["exit"]) for k, v in vi.mine_ctrl.items() if v["exit"] and v["exit"][1] == "stop" and v["exit"][0] != "d0"
         and v["exit"][2] > [t for t in vi.trades if (t["t"], t["d"].isoformat()) == k][0]["entry"] + 1e-9]
print(f"session stop-hit sales above entry (own clone): {len(above)}")

# 4. exploratory registration rule on run_rows.tsv (exact sign-flip on week blocks)
tsv, hdr = {}, None
with open(f"{P}/run_rows.tsv") as fh:
    hdr = fh.readline().rstrip("\n").split("\t")
    for ln in fh:
        f = ln.rstrip("\n").split("\t")
        tsv[(f[0], f[1])] = dict(zip(hdr, f))
arms = [c for c in hdr if c.startswith(("A|", "B|"))]
f = lambda v: None if v in ("", "None", "nan") else float(v)  # noqa: E731
print("\narm             differ weeks  dTot    dEx2    H1      H2     4R(c)  p_exact  meets P1,P3,P4,P5 & p<.05")
for a in arms:
    ks = [k for k in tsv if f(tsv[k]["control"]) is not None and f(tsv[k][a]) is not None]
    dl = {k: f(tsv[k][a]) - f(tsv[k]["control"]) for k in ks}
    differ = [k for k in ks if abs(dl[k]) > 0.005]
    wk = lambda k: date.fromisoformat(k[1]).isocalendar()[:2]  # noqa: E731
    pos = sorted((v for v in dl.values() if v > 1e-12), reverse=True)
    h1 = sum(v for k, v in dl.items() if date.fromisoformat(k[1]) <= date(2026, 6, 30))
    h2 = sum(dl.values()) - h1
    n4 = sum(1 for k in ks if f(tsv[k][a]) >= 4.0 - 1e-9); n4c = sum(1 for k in ks if f(tsv[k]["control"]) >= 4.0 - 1e-9)
    bl = defaultdict(float)
    for k, v in dl.items():
        bl[wk(k)] += v
    nz = [v for v in bl.values() if abs(v) > 1e-9]
    obs = abs(sum(bl.values()))
    if len(nz) <= 20:
        hits = sum(1 for sg in itertools.product((1, -1), repeat=len(nz)) if abs(sum(s * x for s, x in zip(sg, nz))) >= obs - 1e-9)
        p = hits / 2 ** len(nz)
    else:
        p = float("nan")
    tot = sum(dl.values())
    ok = (len(differ) >= 10 and len({wk(k) for k in differ}) >= 6 and tot - sum(pos[:2]) > 0 and h1 > 0 and h2 > 0
          and n4 >= n4c and p < 0.05 and tot > 0)
    print(f"{a:<15} {len(differ):>5} {len({wk(k) for k in differ}):>5} {tot:+7.2f} {tot - sum(pos[:2]):+7.2f} {h1:+7.2f} {h2:+7.2f} "
          f"{n4:>3}({n4c})  {p:7.4f}  {ok}")
