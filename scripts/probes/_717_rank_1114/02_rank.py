#!/usr/bin/env python3
"""#717 slot ranking: R0..R4 compared (2026-11-14; offline, $0, ERA A ONLY; research, no rule changed).

PREREG — written BEFORE any ranking result was computed (01_trend.py only captures two raw per-fire bar measures).
Pool = each night's fires that pass the current list rule (live rules + 1d: OUT when close > 3% under a FALLING 50-day,
i.e. u50 < -0.03 and s50_chg10 < 0). The 5 slots = the top 5 of the pool by the ranking (ties by ticker; NaN ranks last).
Exactly five rankings, no other variants, no weights:
 R0 20-day dollar volume, descending (baseline)
 R1 box ascending, box = hl10 (highest high - lowest low of the last 10 sessions, in daily ranges; shape card)
 R2 trend = mean of the night's percentile ranks (within the pool) of close/SMA200 and the 126-session return; descending
 R3 mean of percentile ranks of (box, tighter = better) and R2's trend score
 R4 mean of percentile ranks of (box tighter = better), trend, and dollar volume
 History: SMA200 / 126-session return use what exists when < 200 / 127 bars, if >= 120 bars; else that component ranks at the median (0.5).
 R3 / R4 use percentile ranks of the trend SCORE (mean of the two component percentiles), re-ranked within the pool.
Metrics per ranking, per era (2017-01..2020-12, 2021-01..2022-03 by the fire day E): Qullamaggie's fired buys in the top 5
 (bridge: R0 must equal 112 in total), High-tier buys in the top 5, big winners in the top 5 (of 26), and on the operator's
 36 graded picks the MEDIAN within-day percentile (1 = ranked best of the pool) of ok/good vs no (IN-SAMPLE; a pick not in the
 pool after 1d is skipped and counted). 'maybe' grades not scored. A sheet is made only if some R1-R4 beats R0 on
 Qullamaggie buys in the top 5 in BOTH eras.

    python3 scripts/probes/_717_rank_1114/01_trend.py > .../01_trend.out ; python3 scripts/probes/_717_rank_1114/02_rank.py > .../02_rank.out
"""
import importlib.util, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SH = os.path.join(REPO, "scripts/probes/_717_shape_1114"); sys.path.insert(0, SH)
import lib  # noqa: E402
spec = importlib.util.spec_from_file_location("m", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
TREND = "/Users/alvinfung/apollo_data/bv1_rank_1114/fires_trend.parquet"
pd.set_option("display.width", 250)

df, cal, big = M.load()
f = df[df.fire].join(pd.read_parquet("/Users/alvinfung/apollo_data/bv1_reasons_1114/fires_measures.parquet"), rsuffix="_m")
sm = pd.read_parquet("/Users/alvinfung/apollo_data/bv1_shape_1114/fires_shape_measures.parquet"); assert (sm.index == f.index).all()
tr = pd.read_parquet(TREND); assert (tr.index == f.index).all()
f = f.join(sm[["hl10"]]).join(tr)
n0 = len(f)
f = f[~((f.u50 < -0.03) & (f.s50_chg10 < 0))].copy()
print(f"fires {n0:,} -> {len(f):,} after 1d; trend NaN (no 120 bars): sma200 {f.sma200_ratio.isna().mean():.2%}, ret126 {f.ret126.isna().mean():.2%}; box NaN {f.hl10.isna().mean():.2%}")

pr = lambda col, asc=True: f.groupby("ci")[col].rank(pct=True, ascending=asc).fillna(0.5)   # higher = better when asc=True
f["p_ratio"], f["p_ret"] = pr("sma200_ratio"), pr("ret126")
f["trend"] = (f.p_ratio + f.p_ret) / 2
f["p_trend"] = pr("trend")
f["p_box"] = pr("hl10", asc=False)          # tighter (smaller) = higher
f["p_dv"] = pr("dollar_vol20")
f["R0"] = f.dollar_vol20
f["R1"] = -f.hl10
f["R2"] = f.trend
f["R3"] = (f.p_box + f.p_trend) / 2
f["R4"] = (f.p_box + f.p_trend + f.p_dv) / 3
RK = ["R0", "R1", "R2", "R3", "R4"]
for r in RK:
    f["rk_" + r] = f.assign(_s=f[r].fillna(-np.inf)).sort_values(["ci", "_s", "ticker"], ascending=[True, False, True]).groupby("ci").cumcount().reindex(f.index) + 1
    f["pct_" + r] = 1 - (f["rk_" + r] - 1) / (f.groupby("ci").ticker.transform("size") - 1).clip(lower=1)

sc = pd.read_csv(os.path.join(REPO, "scripts/probes/_717_reasons_1114/scorecard_rows.tsv"), sep="\t", dtype={"eid": str})
tier = {("d" if s == "dated" else "w") + e: t for s, e, t in zip(sc.set, sc.eid, sc.tier)}
print("scorecard sets:", sc.set.unique().tolist(), "tiers:", sc.tier.value_counts().to_dict())
ERA = {"2017-01..2020-12": lambda E: E <= "2020-12-31", "2021-01..2022-03": lambda E: E > "2020-12-31"}
rows = []
for r in RK:
    top = f[f["rk_" + r] <= 5]
    for en, fn in ERA.items():
        t = top[fn(top.E)]
        ids = {i for l in t.qm for i in l}
        rows.append(dict(rank=r, era=en, qm_top5=len(ids), high=sum(tier.get(i) == "High" for i in ids), big=len(ids & big), picks=len(t)))
res = pd.DataFrame(rows)
tot = res.groupby("rank")[["qm_top5", "high", "big", "picks"]].sum()
print("\n== BRIDGE: R0 total Qullamaggie buys in the daily top 5 (expect 112; big 5) ==", tot.loc["R0", "qm_top5"], tot.loc["R0", "big"])
assert tot.loc["R0", "qm_top5"] == 112
print("(qm_top5 per era is a union within era; total = sum of eras; a buy id never spans eras)")
print(res.to_string(index=False))
print("\nTOTAL"); print(tot)
ref = {e: int(res[(res["rank"] == "R0") & (res.era == e)].qm_top5.iloc[0]) for e in ERA}
print("\nR0 qm_top5 per era:", ref)
beat = [r for r in RK[1:] if all(int(res[(res["rank"] == r) & (res.era == e)].qm_top5.iloc[0]) > ref[e] for e in ERA)]
print("BEATS R0 on Qullamaggie buys in top 5 in BOTH eras:", beat or "NONE")

# graded picks (in-sample)
sys.path.insert(0, os.path.join(REPO, "tests/fixtures"))
from breakout_list_grades import MODEL_PICK_GRADES  # noqa: E402  (fixture dates are now the LIST NIGHT D on all three sheets; lib.load()'s old assert is stale)
Dd = {(t, d): c for t, d, c in zip(df.ticker, [cal[c].isoformat() for c in df.ci], df.ci)}
gr = pd.DataFrame([dict(ticker=g.ticker, grade=g.grade, ci=Dd[(g.ticker, g.list_date)]) for g in MODEL_PICK_GRADES]); assert len(gr) == 36
key = f.reset_index().set_index(["ci", "ticker"])
print("\n== 36 GRADED PICKS: median within-day percentile (1 = ranked best of the pool), IN-SAMPLE ==")
g = gr[gr.grade.isin(["ok", "good", "no"])].copy()
g["grp"] = np.where(g.grade == "no", "no", "ok/good")
inpool = g[[(c, t) in key.index for c, t in zip(g.ci, g.ticker)]].copy()
print(f"graded ok/good+no = {len(g)}; skipped (not in pool after 1d) {len(g) - len(inpool)}: {sorted(set(g.ticker) - set(inpool.ticker))}; scored: ok/good {int((inpool.grp == 'ok/good').sum())}, no {int((inpool.grp == 'no').sum())}")
for r in RK:
    inpool["p"] = [key.loc[(c, t), "pct_" + r] for c, t in zip(inpool.ci, inpool.ticker)]
    m = inpool.groupby("grp").p.median()
    print(f"  {r}: ok/good {m['ok/good']:.2f}  no {m['no']:.2f}  gap {m['ok/good'] - m['no']:+.2f}")
f.to_parquet(os.path.join("/Users/alvinfung/apollo_data/bv1_rank_1114", "pool_ranked.parquet"))
