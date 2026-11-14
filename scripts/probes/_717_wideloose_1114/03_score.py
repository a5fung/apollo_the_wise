#!/usr/bin/env python3
"""#717 wide-and-loose: every Qullamaggie buy + the era-A fires against the frozen line (2026-11-14; offline, $0, ERA A).

PREREG (written before any Qullamaggie buy or fire was scored; the measure and the line are frozen in wl.py / 02_study.out):
 wide = box20_chart, chop = churn20_chart, score = min(wide / WIDE_MIN, chop / CHOP_MIN); WIDE_MIN, CHOP_MIN = the least of
 TDOC / MELI / RRC on each (recomputed here from the graded capture, both TDOC's). "Beyond the line" = score >= 1.
 Sensitivity is reported at >= 0.9 and >= 1.1 (the line is knife-edge: FLGT ties TDOC, THC 0.994, ATYR (ok) 0.975).
 HEADLINE population = buys with a FIXED buy day (269 dated + 354 one-session windows) and a FULL chart (>= 189 bars to
 the night before — every graded chart had 200, so the line is calibrated on a full chart; a shorter history has a
 mechanically smaller chart height and is listed apart). Multi-session windows (incl. the 49 where ratings.tsv picked the
 best-looking session) are scored on every candidate night and reported as any-night / every-night, apart.
 Not-tier buys (funds, IPOs, gap days) are counted with and without.
 Fires: every era-A fire (list nights to 2022-03-31), and the pool after the current list rule 1d (02_rank.py's line).
    python3 scripts/probes/_717_wideloose_1114/03_score.py > scripts/probes/_717_wideloose_1114/03_score.out
"""
import importlib.util, os, sys
from datetime import date
from multiprocessing import get_context
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..")); sys.path.insert(0, HERE)
import wl
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
OUT = "/Users/alvinfung/apollo_data/bv1_wideloose_1114"; os.makedirs(OUT, exist_ok=True)
FIRES = os.path.join(OUT, "fires_wl.parquet")
FULL = 189
G = {}


def _work(tickers):
    P, D, tid = G["P"], G["D"], G["tid"]
    out = []
    for t in tickers:
        g = G["groups"][t]
        cands = [P.runner.bars_for(D, k) for k in tid[t]]
        for i, ci, close in zip(g.index, g.ci, g.close):
            for bars, cidx in cands:
                hit = np.flatnonzero(np.asarray(cidx) == ci)
                if len(hit) and abs(float(bars.c[hit[0]]) - close) < 1e-6 * max(1.0, close):
                    Di = int(hit[0]); a = max(0, Di - 199)
                    w = np.full((4, 200), np.nan)
                    for j, x in enumerate((bars.o, bars.h, bars.l, bars.c)):
                        seg = np.asarray(x[a:Di + 1], float); w[j, 200 - len(seg):] = seg
                    r = wl.core(w[None]).iloc[0]
                    out.append((i, r.box20_chart, r.churn20_chart, r.nbars)); break
            else:
                out.append((i, np.nan, np.nan, np.nan))
    return out


# ── the line, from the graded capture
gr = pd.read_csv(os.path.join(HERE, "graded_rows.tsv"), sep="\t")
WG = np.load(os.path.join(HERE, "graded_windows200.npy"))[gr.wid.to_numpy()]
mg = wl.measures(WG); cg = wl.core(WG)
assert np.allclose(mg.box20_chart, cg.box20_chart) and np.allclose(mg.churn20_chart, cg.churn20_chart) and (mg.nbars == cg.nbars).all()
d3 = gr.ticker.isin(["TDOC", "MELI", "RRC"]).to_numpy()
WIDE_MIN, CHOP_MIN = float(mg.box20_chart[d3].min()), float(mg.churn20_chart[d3].min())
print(f"the line: wide >= {WIDE_MIN:.4f} AND chop >= {CHOP_MIN:.4f} (score >= 1); fast path == full measures on the 48 graded charts: ok")
CUTS = (0.9, 1.0, 1.1)

# ── Qullamaggie's buys
qm = pd.read_csv(os.path.join(HERE, "qm_rows.tsv"), sep="\t", dtype={"eid": str}, keep_default_na=False, na_values=[""])
WQ = np.load(os.path.join(HERE, "qm_windows200.npy"))[qm.wid.to_numpy()]
mq = wl.measures(WQ)
qm["wide"], qm["chop"], qm["legs15"], qm["chart_h"], qm["adr20"] = mq.box20_chart, mq.churn20_chart, mq["swn20_0.15"], mq.chart_h, mq.adr20
qm["score"] = wl.score(mq, WIDE_MIN, CHOP_MIN)
qm["key"] = qm.set + qm.eid
hi = pd.read_csv(os.path.join(REPO, "scripts/probes/_717_context_1114/high_rows.tsv"), sep="\t", dtype={"eid": str})
qm["high_listed"] = qm.key.isin(set((hi.set + hi.eid)[hi.ok == 1])).astype(int)
sc = pd.read_csv(os.path.join(REPO, "scripts/probes/_717_context_1114/scorecard_rows.tsv"), sep="\t", dtype={"eid": str})
fired = set(zip(sc.set + sc.eid, sc.E)[i] for i in range(0)) if False else {(k, e) for k, e, f in zip(sc.set + sc.eid, sc.E, sc.fired) if f == 1}
qm["fired"] = [int((k, e) in fired) for k, e in zip(qm.key, qm.E)]
qm["fixed_day"] = qm.how.isin(["dated", "one_session_window"]).astype(int)
qm.to_csv(os.path.join(HERE, "03_qm_scored.tsv"), sep="\t", index=False)
print(f"\n== QULLAMAGGIE'S 757 BUYS ==\nbuys {qm.key.nunique()}; fixed buy day {qm[qm.fixed_day == 1].key.nunique()} (dated 269 + one-session window 354); multi-session window {qm[qm.fixed_day == 0].key.nunique()}")
fx = qm[qm.fixed_day == 1]
assert fx.key.is_unique
short = fx[fx.nbars < wl.MIN_BARS]; mid = fx[(fx.nbars >= wl.MIN_BARS) & (fx.nbars < FULL)]; H = fx[fx.nbars >= FULL]
print(f"fixed-day buys: full chart (>= {FULL} bars) {len(H)} = HEADLINE; {wl.MIN_BARS}-{FULL - 1} bars {len(mid)} (scored, listed apart); under {wl.MIN_BARS} bars {len(short)} (not scored)")
print(f"headline composition: tier {H.tier.value_counts().to_dict()}; listed High {int(H.high_listed.sum())} of 56; big winners {int(H.big.sum())} of 26; fired (current list + trigger) {int(H.fired.sum())}")
print("score percentiles (headline): " + ", ".join(f"p{p} {np.percentile(H.score, p):.2f}" for p in (10, 50, 90, 95, 99)) + f", max {H.score.max():.2f}")
rows = []
for c in CUTS:
    b = H[H.score >= c]; b2 = mid[mid.score >= c]
    rows.append(dict(cut=c, beyond=len(b), not_tier=int((b.tier == "Not").sum()), ex_not=int((b.tier != "Not").sum()), High=int((b.tier == "High").sum()), Medium=int((b.tier == "Medium").sum()),
                     Low=int((b.tier == "Low").sum()), listed_high_of_56=int(b.high_listed.sum()), big_of_26=int(b.big.sum()), fired=int(b.fired.sum()), short_history_beyond=len(b2)))
print(f"\nbeyond the line, HEADLINE ({len(H)} buys):"); print(pd.DataFrame(rows).to_string(index=False))
cols = ["set", "eid", "ticker", "E", "tier", "reason", "big", "high_listed", "fired", "nbars", "chart_h", "adr20", "wide", "chop", "legs15", "score"]
ff = lambda v: f"{v:.3f}"
print("\nEVERY headline buy at score >= 0.9 (>= 1.0 = as wide and loose as the least of his def-no charts); legs15 = swings of >= 15% of the chart's height in the 20 sessions:")
print(H[H.score >= 0.9].sort_values("score", ascending=False)[cols].to_string(index=False, float_format=ff))
print(f"\nshort history ({wl.MIN_BARS}-{FULL - 1} bars; a smaller chart height by construction) at score >= 0.9:")
print(mid[mid.score >= 0.9].sort_values("score", ascending=False)[cols].to_string(index=False, float_format=ff))
print("\nbig winners (26), most wide-loose first:")
print(fx[fx.big == 1].sort_values("score", ascending=False)[cols].head(8).to_string(index=False, float_format=ff))
print("\nlisted High tier (56), most wide-loose first:")
print(fx[fx.high_listed == 1].sort_values("score", ascending=False)[cols].head(8).to_string(index=False, float_format=ff))
mw = qm[qm.fixed_day == 0]
g = mw.groupby("key").agg(ticker=("ticker", "first"), tier=("tier", "first"), reason=("reason", "first"), nights=("score", "size"), nb=("nbars", "min"), lo=("score", "min"), hi=("score", "max"))
g = g[g.nb >= FULL]
print(f"\nmulti-session windows with a full chart: {len(g)} buys; EVERY candidate night beyond the line: " + ", ".join(f">={c}: {int((g.lo >= c).sum())}" for c in CUTS)
      + " | ANY night: " + ", ".join(f">={c}: {int((g.hi >= c).sum())}" for c in CUTS))
print(g[g.hi >= 0.9].sort_values("hi", ascending=False).to_string(float_format=ff))

# ── era-A fires
spec = importlib.util.spec_from_file_location("m", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
df, cal, big = M.load()
f = df[df.fire].join(pd.read_parquet("/Users/alvinfung/apollo_data/bv1_reasons_1114/fires_measures.parquet"), rsuffix="_m")
if not os.path.exists(FIRES):
    P = M.P; S, _ = P.setup(); D = S.D
    assert D.cal[-1] < date(2025, 1, 1)
    tid = {}
    for k, t in enumerate(D.tickers):
        tid.setdefault(t, []).append(k)
    G.update(P=P, D=D, tid=tid, groups={t: g_ for t, g_ in f.groupby("ticker")})
    ts = sorted(G["groups"])
    with get_context("fork").Pool(8) as pool:
        parts = pool.map(_work, [ts[i::32] for i in range(32)])
    o = pd.DataFrame([r for p in parts for r in p], columns=["idx", "box20_chart", "churn20_chart", "nbars"]).set_index("idx").sort_index()
    assert len(o) == len(f); o.to_parquet(FIRES)
o = pd.read_parquet(FIRES); assert (o.index == f.index).all()
f = f.join(o); f["score"] = wl.score(f, WIDE_MIN, CHOP_MIN)
f["Dd"] = [cal[c].isoformat() for c in f.ci]
assert f.Dd.max() <= "2022-03-31"
for t_, d_ in (("TDOC", "2020-03-19"), ("MELI", "2018-09-17"), ("RRC", "2018-11-12")):       # bridge: the fire path reproduces the graded score
    x = f[(f.ticker == t_) & (f.Dd == d_)].score.iloc[0]; y = wl.score(mg, WIDE_MIN, CHOP_MIN)[(gr.ticker == t_).to_numpy()].iloc[0]
    assert abs(x - y) < 1e-9, (t_, x, y)
nights = df.ci.nunique()
print(f"\n== ERA-A FIRES ==\nfires {len(f):,} over {nights} list nights = {len(f) / nights:.1f} a day; unmatched {int(f.score.isna().sum() - (f.nbars < wl.MIN_BARS).sum())}; under {wl.MIN_BARS} bars {int((f.nbars < wl.MIN_BARS).sum())}; {wl.MIN_BARS}-{FULL - 1} bars {int(((f.nbars >= wl.MIN_BARS) & (f.nbars < FULL)).sum()):,}")
pool = f[~((f.u50 < -0.03) & (f.s50_chg10 < 0))]
f_top = pool.assign(rk=pool.groupby("ci").dollar_vol20.rank(ascending=False, method="first"))
top5 = f_top[f_top.rk <= 5]
allq = {i for l_ in f.qm for i in l_}
tier = {("d" if s == "dated" else "w") + e: t for s, e, t in zip(sc.set, sc.eid, sc.tier)}
print(f"pool after the current list rule (1d): {len(pool):,} = {len(pool) / nights:.1f} a day; the 5 daily slots by dollar volume: {len(top5):,}; Qullamaggie's fired buys among the fires: {len(allq)} (386 on the scorecard; 11 of its sessions are after 2022-03, outside the era-A fires)")
rows = []
for c in CUTS:
    for nm, x in (("all fires", f), ("pool after 1d", pool), ("the 5 daily slots", top5)):
        b = x[x.score >= c]; ids = {i for l_ in b.qm for i in l_}
        rows.append(dict(cut=c, population=nm, n=len(x), removed=len(b), pct=f"{len(b) / len(x):.1%}", per_day_before=round(len(x) / nights, 1), per_day_removed=round(len(b) / nights, 2),
                         removed_full_chart=int((b.nbars >= FULL).sum()), qm_fired_buys_removed=len(ids), qm_high=sum(tier.get(i) == "High" for i in ids), qm_big=len(ids & big),
                         qm_ids=",".join(sorted(ids))[:80]))
print(pd.DataFrame(rows).to_string(index=False))
print("\nwide-loose fires by year (pool after 1d, score >= 1):", pool[pool.score >= 1].Dd.str[:4].value_counts().sort_index().to_dict(), "| all pool fires:", pool.Dd.str[:4].value_counts().sort_index().to_dict())
