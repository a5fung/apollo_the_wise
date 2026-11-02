#!/usr/bin/env python3
"""His 11-02 picks on the blind sample night 2020-05-07 (D GOTU decent, K PDD decent = Qullamaggie's buy, L APT good; the
other 9 not setups). The one rule the backward step nearly admitted — close no more than 0.27 daily ranges under the 21-day
EMA (its threshold = the 2nd percentile of QM's 2017-20 buys) — removes 6 of the 9 (A B C F H J) and keeps all 3. It was held
back only for dropping 6 of QM's 2021-23 buys. On top of the after-labels set: which of QM's buys it drops (-> his charts)
and names a night. No returns read."""
import json, os
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
cols = ["scan_date", "ticker", "pass_history", "pass_universe", "rs_best", "adr20", "pass_prior_move", "prior_move",
        "prior_move.pole_high", "higher_lows.base_low", "close", "e21"]
F = pd.concat([pd.read_parquet(f"/Users/alvinfung/apollo_data/qm_breakouts_1102/features_era{e}.parquet", columns=cols) for e in "AB"], ignore_index=True)
depth = (F["prior_move.pole_high"] - F["higher_lows.base_low"]) / F["prior_move.pole_high"] / F["adr20"]
vs21 = (F.close / F.e21 - 1) / F.adr20
R = {r["feature"]: r for r in json.load(open(f"{HERE}/backward/12_final_rules.json"))["added_rules"]}
Q = pd.read_csv(f"{HERE}/qm_breakouts_v1_gates.tsv.gz", sep="\t")
t = pd.read_csv("/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/replay/trades.tsv.gz", sep="\t", usecols=["eid", "arm", "in_window", "entry_status", "realized_r"])
w = t[(t.arm == "d3_p33_tspd") & (t.in_window == True) & (t.entry_status == "filled")]
Q["big"] = Q.eid.isin(set(w[w.realized_r >= 5].eid))
idx = pd.Series(F.index, index=pd.MultiIndex.from_arrays([F.ticker, F.scan_date]))
Q["row"] = [idx.get((a, b)) for a, b in zip(Q.ticker, Q.D)]
LRN = float(depth.loc[Q.row[(Q.sym == "LRN") & (Q.E == "2020-08-05")]].iloc[0])
S0 = (F.pass_history == 1) & (F.pass_universe == 1) & (F.rs_best >= 35) & (F.adr20 >= 0.021) & (F.pass_prior_move == 1)
AFTER = S0 & depth.between(LRN, R["base_depth_adr"]["hi"]) & (F.prior_move >= R["prior_move"]["threshold"])
NO = {("YPF", "2019-04-17"), ("MRNA", "2021-11-29"), ("W", "2020-04-07"), ("DOCU", "2020-12-04"), ("DOCU", "2020-12-15"), ("SQM", "2021-09-10")}
fit = Q[Q.E < "2021-01-01"]
th = float(np.sort(vs21.loc[fit.row].values)[3])        # same order statistic as the backward step (4th smallest of 162)
lines = [f"close-vs-EMA21 threshold (4th smallest of QM's 162 2017-20 buys): {th:.4f} daily ranges"]
for name, m in (("after his labels", AFTER), ("after his labels + close vs EMA21 rule", AFTER & (vs21 >= th))):
    n = m.groupby(F.scan_date).sum(); kept = m.loc[Q.row].values
    lines.append(f"{name:42s} his buys {int(kept.sum())}/269 | big winners {int(kept[Q.big.values].sum())}/26 | names a night median {n.median():.0f} mean {n.mean():.0f} p90 {n.quantile(.9):.0f}")
drop = Q[AFTER.loc[Q.row].values & ~(vs21 >= th).loc[Q.row].values].copy()
drop["vs21"] = vs21.loc[drop.row].values
lines.append(f"\nQM buys the EMA21 rule newly drops ({len(drop)}):")
for r in drop.sort_values("E").itertuples():
    lines.append(f"  {r.sym:6s} buy {r.E}  close {r.vs21:+.2f} daily ranges vs EMA21  {'BIG WINNER' if r.big else ''}")
drop[["eid", "sym", "ticker", "D", "E", "vs21", "big"]].to_csv(f"{HERE}/15_ema21_drops.tsv", sep="\t", index=False)
print("\n".join(lines)); open(f"{HERE}/15_ema21_rule.txt", "w").write("\n".join(lines) + "\n")
