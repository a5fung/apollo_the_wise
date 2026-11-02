#!/usr/bin/env python3
"""After his 11-02 labels on the 11 dropped buys: the rules that dropped his GOOD ones are loosened just enough to keep them
(daily range back to the start's 2.1% for EW 2.11% / LMT 2.6-2.7%; the shallow-base limit down to LRN's 1.511 daily ranges);
the 32.1% run-up rule stays (it dropped only his 'no's). Counts his buys kept and names a night. No returns read."""
import json, os
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
cols = ["scan_date", "ticker", "pass_history", "pass_universe", "rs_best", "adr20", "pass_prior_move", "prior_move",
        "prior_move.pole_high", "higher_lows.base_low"]
F = pd.concat([pd.read_parquet(f"/Users/alvinfung/apollo_data/qm_breakouts_1102/features_era{e}.parquet", columns=cols) for e in "AB"], ignore_index=True)
depth = (F["prior_move.pole_high"] - F["higher_lows.base_low"]) / F["prior_move.pole_high"] / F["adr20"]
S0 = (F.pass_history == 1) & (F.pass_universe == 1) & (F.rs_best >= 35) & (F.adr20 >= 0.021) & (F.pass_prior_move == 1)
Q = pd.read_csv(f"{HERE}/qm_breakouts_v1_gates.tsv.gz", sep="\t")
t = pd.read_csv("/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/replay/trades.tsv.gz", sep="\t", usecols=["eid", "arm", "in_window", "entry_status", "realized_r"])
w = t[(t.arm == "d3_p33_tspd") & (t.in_window == True) & (t.entry_status == "filled")]
Q["big"] = Q.eid.isin(set(w[w.realized_r >= 5].eid))
idx = pd.Series(F.index, index=pd.MultiIndex.from_arrays([F.ticker, F.scan_date]))
Q["row"] = [idx.get((a, b)) for a, b in zip(Q.ticker, Q.D)]
GOOD = {("EW", "2019-08-16"), ("LMT", "2022-04-05"), ("LMT", "2022-04-06"), ("LRN", "2020-08-05")}
NO = {("YPF", "2019-04-17"), ("MRNA", "2021-11-29"), ("W", "2020-04-07"), ("DOCU", "2020-12-04"), ("DOCU", "2020-12-15"), ("SQM", "2021-09-10")}
R = {r["feature"]: r for r in json.load(open(f"{HERE}/backward/12_final_rules.json"))["added_rules"]}
A, DLO, DHI, PM = R["adr20"]["threshold"], R["base_depth_adr"]["lo"], R["base_depth_adr"]["hi"], R["prior_move"]["threshold"]
LRN = float(depth.loc[Q.row[(Q.sym == "LRN") & (Q.E == "2020-08-05")]].iloc[0])
out = []
def rep(name, m):
    n = m.groupby(F.scan_date).sum(); kept = m.loc[Q.row].values
    lab = lambda S: f"{sum(kept[i] for i, (s, e) in enumerate(zip(Q.sym, Q.E)) if (s, e) in S)}/{sum((s, e) in S for s, e in zip(Q.sym, Q.E))}"
    line = (f"{name:58s} his buys {int(kept.sum())}/269 | big winners {int(kept[Q.big.values].sum())}/26 | his GOOD labels kept {lab(GOOD)} | "
            f"his NO labels kept {lab(NO)} | names a night median {n.median():.0f} mean {n.mean():.0f} p90 {n.quantile(.9):.0f}")
    print(line); out.append(line)
rep("start (strength 35, range 2.1%, run-up rule as v1)", S0)
rep("backward result (range 2.8%, depth 1.70-8.98, run-up 32.1%)", S0 & (F.adr20 >= A) & depth.between(DLO, DHI) & (F.prior_move >= PM))
rep("AFTER HIS LABELS (range 2.1%, depth 1.511-8.98, run-up 32.1%)", S0 & depth.between(LRN, DHI) & (F.prior_move >= PM))
open(f"{HERE}/14_after_his_labels.txt", "w").write("\n".join(out) + "\n")
