#!/usr/bin/env python3
"""#717 lower-line check — BRIDGE + SCORE on era A (2026-11-14; post-processing of 01_capture.py; research, no rule changed).
THE CHECK (ll.py): OUT when V3 > 0.212 AND the 30-session lower line is flat or falling, with >= 189 bars to D.
Pool = _717_context_1114/05_sheet.py's stack: 1d (close > 3% under a 50-day lower than 10 sessions ago) + A2(10)
(50-day lower than 10 sessions ago AND a negative 126-session return; a blank return passes).
Qullamaggie buys: ctx.load()'s scorecard rows on their 200-bar fixture windows; a buy is LOST when none of its fired
sessions survives (02_score.py's convention); flagged sessions of big winners / High buys are printed even if the buy survives.

    python3 scripts/probes/_717_lowline_1114/02_score.py > scripts/probes/_717_lowline_1114/02_score.out
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_context_1114"))
import ll, ctx  # noqa: E402
pd.set_option("display.width", 250)
OUTD = "/Users/alvinfung/apollo_data/bv1_lowline_1114"
def load():
    """ctx.load() minus its 36-grade block (the grades fixture is 48 now and ctx.load asserts 36; the grades are bridged below
    from _717_wideloose_1114/graded_rows.tsv instead). Fires / scorecard / High rows built exactly as ctx.load builds them."""
    df = pd.read_parquet(ctx.CAP)
    cal = [ctx.date.fromisoformat(s) for s in open(ctx.CAP + ".cal.txt").read().split()]
    assert cal[-1] < ctx.date(2025, 1, 1)
    nights = sorted(df.ci.unique())
    f = df[df.fire].join(pd.read_parquet(ctx.MEASF), rsuffix="_m"); assert (f.base_len == f.base_len_m).all()
    tr = pd.read_parquet(ctx.TRENDF); assert (tr.index == f.index).all(); f = f.join(tr)
    f["Dd"] = [cal[c].isoformat() for c in f.ci]; f["Ed"] = [cal[c + 1].isoformat() for c in f.ci]
    assert f.Dd.max() <= "2022-03-31"
    CX = os.path.join(REPO, "scripts/probes/_717_context_1114")
    WX = np.load(os.path.join(CX, "fixtures_windows200.npy"))
    def fx(name, keys):
        a = pd.read_csv(os.path.join(ctx.PREV, name), sep="\t", dtype={"eid": str})
        b = pd.read_csv(os.path.join(CX, name), sep="\t", dtype={"eid": str})
        assert len(a) == len(b) and all((a[k].astype(str) == b[k].astype(str)).all() for k in keys), name
        a["w"] = b.wid; return a
    sc = fx("scorecard_rows.tsv", ["set", "eid", "E", "fired"]); sc["key"] = sc.set + sc.eid; sc["w"] = sc.w.astype(int)
    sc["ret126"] = ctx.ret126_of(WX[sc.w.to_numpy()]); assert sc.E.max() < "2025-01-01"
    hi_all = fx("high_rows.tsv", ["set", "eid", "E", "ok"]); hi = hi_all[hi_all.ok == 1].copy(); hi["w"] = hi.w.astype(int)
    assert len(hi) == 56
    return f, sc, hi, nights, cal, WX
f, sc, hi, nights, cal, WX = load()
m = pd.read_parquet(os.path.join(OUTD, "fires_lowline.parquet")); assert (m.index == f.index).all()
WW = np.load(os.path.join(OUTD, "fires_windows200.npy"), mmap_mode="r"); assert len(WW) == len(f)
f = f.join(m); f["pos"] = np.arange(len(f))
f["OUT"] = ll.flag(f.V3, f.LS30, f.nbars)
assert (f.matched == 1).all()
ONE_D = lambda d: ~((d.u50 < -0.03) & (d.s50_chg10 < 0))
A2 = lambda d: ~((d.s50_chg10 < 0) & (d.ret126 < 0))

# ── BRIDGE
print("== BRIDGE ==")
for t, Dn, v, s in (("MELI", "2018-09-17", 0.484, -0.002), ("TDOC", "2020-03-19", 0.244, -0.037)):
    x = f[(f.ticker == t) & (f.Dd == Dn)]; assert len(x) == 1
    r = x.iloc[0]
    ok = round(r.V3, 3) == v and round(r.LS30, 3) == s
    print(f"  {t} list night {Dn} (fire path): V3 {r.V3:.3f} (expect {v}), slope {r.LS30:+.3f} (expect {s:+.3f}), bars {int(r.nbars)}, flagged {bool(r.OUT)} -> {'REPRODUCED' if ok else 'MISMATCH'}")
    assert ok
gw = pd.read_csv(os.path.join(REPO, "scripts/probes/_717_wideloose_1114/graded_rows.tsv"), sep="\t")
WG = np.load(os.path.join(REPO, "scripts/probes/_717_wideloose_1114/graded_windows200.npy"))[gw.wid.to_numpy()]
same_w, rows = 0, []
for k, g in enumerate(gw.itertuples()):
    x = f[(f.ticker == g.ticker) & (f.Dd == g.D)]; assert len(x) == 1, g
    r = x.iloc[0]
    same_w += np.allclose(np.asarray(WW[r.pos], float), WG[k, :4], rtol=1e-6, equal_nan=True)
    rows.append(dict(ticker=g.ticker, D=g.D, grade=g.grade, V3=r.V3, LS=r.LS30, nb=r.nbars, OUT=bool(r.OUT)))
gg = pd.DataFrame(rows)
V, L, n = ll.measure(WG); gg["V3_fx"], gg["LS_fx"] = V, L
print(f"  48 graded charts: fire-path window == wideloose graded window on {same_w}/48; V3 equal {int(np.isclose(gg.V3, gg.V3_fx, equal_nan=True).sum())}/48, slope equal {int(np.isclose(gg.LS, gg.LS_fx, equal_nan=True).sum())}/48")
fl = sorted(gg[gg.OUT].ticker)
print(f"  graded flagged: {fl} (expect COUP DVAX MELI RRC TDOC TWTR WPX); VUZI (ok, the edge row): V3 {gg[gg.ticker=='VUZI'].V3.iloc[0]:.3f} slope {gg[gg.ticker=='VUZI'].LS.iloc[0]:+.4f} -> {'flagged' if gg[gg.ticker=='VUZI'].OUT.iloc[0] else 'kept'}")
assert same_w == 48 and fl == ["COUP", "DVAX", "MELI", "RRC", "TDOC", "TWTR", "WPX"]
print("  graded grades flagged:", gg[gg.OUT].grade.value_counts().to_dict(), "| graded under 189 bars (not scoreable):", gg[gg.nb < 189][["ticker", "grade", "nb"]].values.tolist())
f1 = f[ONE_D(f)]; pool = f1[A2(f1)]
print(f"  pool: fires {len(f):,} -> {len(f1):,} after 1d -> {len(pool):,} after 1d + A2(10) (expect 156,695 / 136,305 / 120,872)")
assert (len(f), len(f1), len(pool)) == (156695, 136305, 120872)

def perday(d):
    p = d.groupby("ci").size().reindex(nights).fillna(0)
    return p.median(), p.mean()
print(f"\n== FIRES A DAY (median / mean over {len(nights)} era-A list nights) ==")
print(f"  fires under 189 bars (not scoreable, pass): {int((f.nbars < 189).sum()):,} of {len(f):,}")
for nm, d in (("all fires", f), ("pool after 1d + A2(10)", pool)):
    a, b = perday(d), perday(d[~d.OUT])
    print(f"  {nm:24s}: {a[0]:.0f} / {a[1]:.1f} -> {b[0]:.0f} / {b[1]:.1f} with the check; removed {int(d.OUT.sum()):,} of {len(d):,} ({d.OUT.mean():.2%}), {a[1] - b[1]:.2f} a day on average")
TOP = lambda d: set(map(tuple, d.sort_values("dollar_vol20", ascending=False).groupby("ci").head(5)[["ci", "ticker"]].to_numpy()))
t0, t1 = TOP(pool), TOP(pool[~pool.OUT])
print(f"  top-5 dollar-volume picks of the pool replaced by the check: {1 - len(t0 & t1) / len(t0):.1%}")

# ── Qullamaggie
print("\n== QULLAMAGGIE SCORECARD BUYS ==")
V, L, n = ll.measure(WX[sc.w.to_numpy()]); sc["V3"], sc["LS30"], sc["nbars"] = V, L, n; sc["OUT"] = ll.flag(V, L, n)
V, L, n = ll.measure(WX[hi.w.to_numpy()]); hi["OUT"] = ll.flag(V, L, n); hi["nbars"] = n
print(f"  listed High-tier buys (56): flagged {int(hi.OUT.sum())}: {hi[hi.OUT][['ticker', 'E']].values.tolist()}; under 189 bars {int((hi.nbars < 189).sum())}")
F = sc[sc.fired == 1]
def lost(keep):
    s = F[keep(F)]
    return F[~F.key.isin(s.key)].drop_duplicates("key")
base_keep = lambda d: ONE_D(d) & A2(d)
for nm, kp, ref in (("check alone", lambda d: ~d.OUT, None), ("1d + A2(10) + check, beyond 1d + A2(10)", lambda d: base_keep(d) & ~d.OUT, base_keep)):
    x = lost(kp)
    if ref is not None:
        x = x[~x.key.isin(lost(ref).key)]
    print(f"  {nm}: fired buys lost {len(x)} of {F.key.nunique()}; tiers {x.tier.value_counts().to_dict()}; big winners {int(x.big.sum())}: "
          + ", ".join(f"{r.ticker} {r.E} ({r.tier}{', BIG' if r.big else ''})" for r in x.itertuples()))
fs = F[F.OUT]
print(f"  fired sessions flagged: {len(fs)} of {len(F)} ({fs.key.nunique()} buys); of big winners: {fs[fs.big == 1][['ticker', 'E']].values.tolist()}; of High tier: {fs[fs.tier == 'High'][['ticker', 'E']].values.tolist()}")
print(f"  scorecard fired sessions under 189 bars (not scoreable): {int((F.nbars < 189).sum())}")
bl = lost(lambda d: ~d.OUT); bl = bl[bl.big == 1]
print("BIG WINNERS LOST:", len(bl), "-> STOP" if len(bl) else "-> none, sheet may be drawn")
open(os.path.join(HERE, "02_big_lost.txt"), "w").write(str(len(bl)) + "\n")
