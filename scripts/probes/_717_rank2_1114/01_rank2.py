#!/usr/bin/env python3
"""#717 slot ranking, round 2: L0 / R0 / PM on the pool AFTER ALL THREE live list checks (2026-11-14; offline, $0,
ERA A ONLY (list nights 2017-01..2022-03-31), research, no rule changed, nothing deployed).

PREREG — written BEFORE any number of this probe was computed. ALREADY SEEN when registering (disclosed): the all-fires
results (_717_pick_model_1113/02_test.out: test era model 41 / order score 18 / dollar volume 43) and the 1d-only pool
(_717_rank_1114/02_rank.out: dollar volume 112 = 63 + 49). NOT seen: anything on the three-check pool.

POOL = each night's fires (M.load(), the 4% list capture) that pass all three live context checks, from the saved flags:
  1d  sma50_falling_under : OUT when u50 < -0.03 and s50_chg10 < 0
  A2  downtrend_6m        : OUT when s50_chg10 < 0 and ret126 < 0 (a blank return passes)
  LL  lower_line          : OUT when nbars >= 189 and V3 > 0.2123 (signed, strict) and LS30 <= 0
  BRIDGE (assert): fires 156,695 -> 136,305 -> 120,872 -> 114,847.
VARIANTS, exactly three (+ one disclosed sensitivity of L0), top 5 a day, ties by ticker, a missing score last:
  L0  live order_score = mean within-night percentile of runup6m_adr (bigger first) and spread10_adr (tighter first),
      as M.load() computes it (percentile inside the night's 4% list BEFORE the context checks; bridges to 1113).
  L0b SENSITIVITY ONLY: the same score re-percentiled inside the night's gated FIRE pool. Live takes the percentile
      inside the gated LIST (gates run before rank_rows); the saved flags exist for fire rows only, so live sits
      between L0 and L0b. Not a candidate.
  R0  20-day dollar volume, descending.
  PM  the pick model, primary, coef.json as fitted 2017-2020 (features = percentile inside the night's 4% list, as
      fitted; NO refit, no re-percentiling). 2017-2020 is IN-SAMPLE for PM; only 2021-01..2022-03 is a fair read.
ERAS by the fire day E: 2017-01..2020-12 (E <= 2020-12-31) and 2021-01..2022-03 (E > 2020-12-31).
METRICS per variant per era: distinct Qullamaggie buys in the day's top 5 (taken_set = ids of the `qm` lists, the 112
  convention), High-tier among them (scorecard_rows.tsv tier), big winners among them (of 26), and top-5 rows on a buy
  (name-days, additive across days).
BRIDGES before any new number (assert): R0 on the 1d pool = 112 (63 / 49, 5 big); on all test-era fires PM 41 / L0 18 / R0 43.
BREAK ORDER: the 1113 probe has NO minute-bar replay (its own words: "daily bars cannot see WHICH name breaks first").
  None is built here. Reused daily-bar brackets on the gated pool only: K = the day's top 5 fires by the ranking (best
  case, the headline metric) and G = names above the level at the open first, then by rank (rank re-percentiled in the
  pool). "R as wired" is skipped: it needs non-fire list rows (no context flags saved) and models resting orders that
  break-only slots replaced.
COST: buys L0's top 5 holds that R0 / PM drop, and R0 vs PM, by name with tier and big flag. Pool cost (known, 06_all_three.out):
  362 of 380 fired scorecard buys survive the three checks, 0 High and 0 big lost.
GRADED PICKS (IN-SAMPLE, and SELECTION-BIASED: sheets 1113/1113B were drawn from the top of PM, 1114/1114B/1114C from
  the top of dollar volume — under the ranking that drew a sheet both groups sit near the top by construction): median
  within-night percentile in the pool (1 = ranked best) of ok/good vs no, pooled AND split by which ranking drew the
  sheet. 'conditional' not scored; a pick not in the three-check pool is skipped and counted.
PASS / FAIL BAR:
  A variant BEATS L0 if it has more distinct Qullamaggie buys in the top 5 than L0 in BOTH eras AND at least as many big
  winners in total. PM vs R0 TIE RULE: the simpler R0 is recommended unless PM beats R0 in the 2021-01..2022-03 era on
  distinct buys AND the day-resampled (1,000 draws of days, seed 717) 90% interval of the NAME-DAY difference excludes 0
  (name-days are additive, so the interval is valid; distinct-buy differences are reported as points only).
  If neither beats L0: recommend no change.

    python3 scripts/probes/_717_rank2_1114/01_rank2.py > scripts/probes/_717_rank2_1114/01_rank2.out 2> scripts/probes/_717_rank2_1114/01_rank2.err
"""
import importlib.util, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUTD = "/Users/alvinfung/apollo_data/bv1_rank2_1114"
spec = importlib.util.spec_from_file_location("m", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
P2, taken = M.P2, M.taken_set
pd.set_option("display.width", 250)

df, cal, big = M.load()
assert max(cal[c] for c in df.ci.unique()).isoformat() <= "2022-03-31"
co = json.load(open(M.COEF))["models"]["primary"]
df["PM"] = M.X_of(df, co["features"]) @ np.r_[co["intercept"], co["coef"]]
df["L0"], df["R0"] = df.score_order, df.dollar_vol20
f = df[df.fire].copy()
for p, cols in (("bv1_reasons_1114/fires_measures.parquet", ["u50", "s50_chg10"]), ("bv1_rank_1114/fires_trend.parquet", ["ret126"]),
                ("bv1_lowline_1114/fires_lowline.parquet", ["V3", "LS30", "nbars"])):
    m = pd.read_parquet("/Users/alvinfung/apollo_data/" + p); assert (m.index == f.index).all(), p
    f[cols] = m[cols].to_numpy()
one_d = ~((f.u50 < -0.03) & (f.s50_chg10 < 0))
a2 = ~((f.s50_chg10 < 0) & (f.ret126 < 0))
ll = ~((f.nbars >= 189) & (f.V3 > 0.2123) & (f.LS30 <= 0))
counts = (len(f), int(one_d.sum()), int((one_d & a2).sum()), int((one_d & a2 & ll).sum()))
print("== BRIDGE 1 pool: fires -> 1d -> +A2(10) -> +lower line:", counts, "(expect 156695, 136305, 120872, 114847)")
assert counts == (156695, 136305, 120872, 114847)
ERA = {"2017-01..2020-12": lambda E: E <= "2020-12-31", "2021-01..2022-03": lambda E: E > "2020-12-31"}
f1 = f[one_d]; t = P2.top_k(f1, f1.R0)
b = [len(taken(t[fn(t.E)])) for fn in ERA.values()]
print("== BRIDGE 2 R0 on the 1d pool:", b, "total", sum(b), "big", len(taken(t) & big), "(expect 63, 49, 112, 5)")
assert b == [63, 49] and len(taken(t) & big) == 5
ft = f[f.E >= "2021-01-01"]
b3 = [len(taken(P2.top_k(ft, ft[c]))) for c in ("PM", "L0", "R0")]
print("== BRIDGE 3 all test-era fires PM / L0 / R0:", b3, "(expect 41, 18, 43)")
assert b3 == [41, 18, 43]

pool = f[one_d & a2 & ll].copy()
g = pool.groupby("ci")
pool["L0b"] = (g.runup6m_adr.rank(pct=True, ascending=True) + g.spread10_adr.rank(pct=True, ascending=False)) / 2
VAR = ["L0", "L0b", "R0", "PM"]
n_day = g.ticker.transform("size")
for v in VAR:
    x = pool.assign(_s=pool[v]).sort_values(["ci", "_s", "ticker"], ascending=[True, False, True], na_position="last")
    pool["rk_" + v] = (x.groupby("ci").cumcount() + 1).reindex(pool.index)
    pool["pct_" + v] = 1 - (pool["rk_" + v] - 1) / (n_day - 1).clip(lower=1)
    pool["G_" + v] = pool["pct_" + v] + pool.f_open_above          # open-above first, then rank
pool.drop(columns=["qm"]).assign(qm=pool.qm.map(lambda l: ",".join(l))).to_parquet(os.path.join(OUTD, "pool3_ranked.parquet"))

sc = pd.read_csv(os.path.join(REPO, "scripts/probes/_717_reasons_1114/scorecard_rows.tsv"), sep="\t", dtype={"eid": str})
tier = {("d" if s == "dated" else "w") + e: t_ for s, e, t_ in zip(sc.set, sc.eid, sc.tier)}
tk_of = {("d" if s == "dated" else "w") + e: (t_, E) for s, e, t_, E in zip(sc.set, sc.eid, sc.ticker, sc.E)}
nm = lambda i: f"{tk_of.get(i, ('?', '?'))[0]} {tk_of.get(i, ('?', '?'))[1]} ({tier.get(i, '?')}{', BIG' if i in big else ''})"

rows, SETS = [], {}
for mode, pre in (("K top 5 fires by rank (best case)", "rk_"), ("G open-above first, then rank (bracket)", "G_")):
    for v in VAR:
        top = pool[pool["rk_" + v] <= 5] if pre == "rk_" else P2.top_k(pool, pool["G_" + v])
        for en, fn in ERA.items():
            x = top[fn(top.E)]; ids = taken(x)
            SETS[(mode[0], v, en)] = (ids, x)
            px = pool[fn(pool.E)]
            rows.append(dict(mode=mode, variant=v, era=en, qm_top5=len(ids), high=sum(tier.get(i) == "High" for i in ids), big=len(ids & big),
                             name_days=int(x.is_qm.sum()), picks=len(x), days=x.ci.nunique(),
                             pool_fired_buys=len(taken(px)), pool_high=sum(tier.get(i) == "High" for i in taken(px)), pool_big=len(taken(px) & big)))
res = pd.DataFrame(rows)
res.to_csv(os.path.join(HERE, "01_results.tsv"), sep="\t", index=False)
print("\n== RESULT TABLE (pool after all three checks; qm_top5 = distinct Qullamaggie buys in the day's top 5; pool_* = what fires in the pool at all) ==")
print(res.to_string(index=False))
tot = res.groupby(["mode", "variant"], sort=False)[["qm_top5", "high", "big", "name_days", "picks"]].sum()
print("\nTOTAL both eras"); print(tot)

print("\n== PASS / FAIL (mode K, the registered headline) ==")
K = res[res["mode"].str.startswith("K")].set_index(["variant", "era"])
for v in ("R0", "PM"):
    both = all(K.loc[(v, e), "qm_top5"] > K.loc[("L0", e), "qm_top5"] for e in ERA)
    bigok = sum(K.loc[(v, e), "big"] for e in ERA) >= sum(K.loc[("L0", e), "big"] for e in ERA)
    print(f"  {v} vs L0: " + "; ".join(f"{e} {K.loc[(v, e), 'qm_top5']} vs {K.loc[('L0', e), 'qm_top5']} ({K.loc[(v, e), 'qm_top5'] - K.loc[('L0', e), 'qm_top5']:+d})" for e in ERA)
          + f"; big {sum(K.loc[(v, e), 'big'] for e in ERA)} vs {sum(K.loc[('L0', e), 'big'] for e in ERA)} -> {'BEATS L0' if both and bigok else 'DOES NOT BEAT L0'}")

print("\n== DAY RESAMPLE, 1,000 draws of days, seed 717: 90% interval of the NAME-DAY difference (additive) ==")
for en, fn in ERA.items():
    px = pool[fn(pool.E)]; days = np.array(sorted(px.ci.unique()))
    per = {v: SETS[("K", v, en)][1].groupby("ci").is_qm.sum().reindex(days).fillna(0).to_numpy() for v in VAR}
    dr = np.random.default_rng(717).integers(0, len(days), size=(1000, len(days)))
    for a, b_ in (("R0", "L0"), ("PM", "L0"), ("PM", "R0"), ("R0", "L0b"), ("PM", "L0b")):
        d = (per[a] - per[b_])[dr].sum(1); lo, hi = np.percentile(d, [5, 95])
        pd_ = len(SETS[("K", a, en)][0]) - len(SETS[("K", b_, en)][0])
        print(f"  {en}  {a} minus {b_}: name-days {int((per[a] - per[b_]).sum()):+d} (90% {lo:+.0f} .. {hi:+.0f}) {'excludes 0' if lo > 0 or hi < 0 else 'includes 0'} | distinct buys {pd_:+d} (point only)")
e2 = "2021-01..2022-03"
print("  (PM vs R0 tie rule reads the 2021-01..2022-03 line above: PM must be ahead on distinct buys AND the interval must exclude 0; else R0)")

print("\n== COST: buys one ranking's top 5 holds that the other drops (mode K), by name ==")
for a, b_ in (("L0", "R0"), ("L0", "PM"), ("R0", "PM"), ("PM", "R0")):
    for en in ERA:
        lost = sorted(SETS[("K", a, en)][0] - SETS[("K", b_, en)][0], key=lambda i: tk_of.get(i, ("?", "?")))
        print(f"  {en}: in {a}'s top 5, not in {b_}'s: {len(lost)} (High {sum(tier.get(i) == 'High' for i in lost)}, big {len(set(lost) & big)}): " + "; ".join(nm(i) for i in lost))
print("  big winners in the top 5, by variant: " + " | ".join(f"{v}: " + ", ".join(sorted(nm(i) for en in ERA for i in SETS[('K', v, en)][0] & big)) for v in VAR))
print("  High-tier in the top 5, by variant: " + " | ".join(f"{v}: " + ", ".join(sorted(nm(i) for en in ERA for i in SETS[('K', v, en)][0] if tier.get(i) == 'High')) for v in VAR))

# ── graded picks (in-sample, selection-biased)
sys.path.insert(0, os.path.join(REPO, "tests/fixtures"))
from breakout_list_grades import MODEL_PICK_GRADES  # noqa: E402
print(f"\n== GRADED PICKS: {len(MODEL_PICK_GRADES)} picks, list nights {min(g_.list_date for g_ in MODEL_PICK_GRADES)} .. {max(g_.list_date for g_ in MODEL_PICK_GRADES)} "
      "(ALL in era A — they resolve in the era-A capture; no live-list bars needed). IN-SAMPLE + SELECTION-BIASED ==")
assert max(g_.list_date for g_ in MODEL_PICK_GRADES) <= "2022-03-31"
key = pool.assign(Dd=[cal[c].isoformat() for c in pool.ci]).set_index(["ticker", "Dd"])
fkey = set(zip(f.ticker, [cal[c].isoformat() for c in f.ci]))
src = lambda s: "drawn from PM" if "_717_pick_model_1113" in s else "drawn from dollar volume"
G_ = []
for g_ in MODEL_PICK_GRADES:
    k = (g_.ticker, g_.list_date)
    G_.append(dict(ticker=g_.ticker, D=g_.list_date, grade=g_.grade, src=src(g_.sheet), sheet=os.path.basename(g_.sheet), is_fire=k in fkey, in_pool=k in key.index,
                   **{v: (float(key.loc[k, "pct_" + v]) if k in key.index else np.nan) for v in VAR}))
gr = pd.DataFrame(G_); gr.to_csv(os.path.join(HERE, "01_graded.tsv"), sep="\t", index=False)
print("grades:", gr.grade.value_counts().to_dict(), "| not a fire row in the capture:", gr[~gr.is_fire].ticker.tolist(),
      "| removed by the three checks:", gr[gr.is_fire & ~gr.in_pool][["ticker", "grade"]].values.tolist())
s = gr[gr.in_pool & gr.grade.isin(["ok", "good", "no"])].copy(); s["grp"] = np.where(s.grade == "no", "no", "ok/good")
print(f"scored (in pool, not conditional): {len(s)}  ok/good {int((s.grp == 'ok/good').sum())}  no {int((s.grp == 'no').sum())}")
for lab, d in [("ALL sheets", s)] + [(k_, d_) for k_, d_ in s.groupby("src")]:
    print(f" {lab}: ok/good n={int((d.grp == 'ok/good').sum())}, no n={int((d.grp == 'no').sum())}")
    for v in VAR:
        md = d.groupby("grp")[v].median()
        print(f"   {v:3s}: ok/good {md.get('ok/good', np.nan):.2f}  no {md.get('no', np.nan):.2f}  gap {md.get('ok/good', np.nan) - md.get('no', np.nan):+.2f}")
