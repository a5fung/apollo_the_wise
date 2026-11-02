#!/usr/bin/env python3
"""Next candidate from his 2020-05-07 picks: close vs the 50-day SMA (A COLD -1.7%, B GLNG -16.7% are his rejects still on the
list after the loosened EMA21 rule; his picks sit at +0.4% / +7.6% / +23.9%). Limit = the 4th smallest of QM's 162 2017-20
buys (the backward step's convention), on top of the EMA21-loosened list. Lists QM buys it drops (-> his charts). No returns."""
import json, os, runpy
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
g = runpy.run_path(f"{HERE}/15_ema21_rule.py", run_name="lib")
F, Q, AFTER, vs21 = g["F"], g["Q"], g["AFTER"], g["vs21"]
d = pd.read_csv(f"{HERE}/15_ema21_drops.tsv", sep="\t")
th21 = float(d.loc[d.sym == "TSLA", "vs21"].iloc[0])
s50 = pd.concat([pd.read_parquet(f"/Users/alvinfung/apollo_data/qm_breakouts_1102/features_era{e}.parquet", columns=["breakdown.sma50"]) for e in "AB"], ignore_index=True)["breakdown.sma50"]
vs50 = F.close / s50 - 1
CUR = AFTER & (vs21 >= th21)
fit = Q[Q.E < "2021-01-01"]
th = float(np.sort(vs50.loc[fit.row].values)[3])
lines = [f"\nclose vs 50-day SMA limit (4th smallest of QM's 162 2017-20 buys): {th:+.2%}"]
for name, m in (("current (EMA21 loosened)", CUR), ("+ close vs 50-day SMA rule", CUR & (vs50 >= th))):
    n = m.groupby(F.scan_date).sum(); kept = m.loc[Q.row].values
    lines.append(f"{name:30s} his buys {int(kept.sum())}/269 | big winners {int(kept[Q.big.values].sum())}/26 | names a night median {n.median():.0f} mean {n.mean():.0f} p90 {n.quantile(.9):.0f}")
drop = Q[CUR.loc[Q.row].values & ~(vs50 >= th).loc[Q.row].values].copy()
drop["vs50"] = vs50.loc[drop.row].values
lines.append(f"QM buys it drops: {len(drop)} " + ", ".join(f"{r.sym} {r.E} ({r.vs50:+.1%}){' BIG' if r.big else ''}" for r in drop.sort_values('E').itertuples()))
drop[["eid", "sym", "ticker", "D", "E", "vs50", "big"]].to_csv(f"{HERE}/18_sma50_drops.tsv", sep="\t", index=False)
k = json.load(open(f"{HERE}/charts/sample_night_KEY.json"))["key"]
night = F[F.scan_date == "2020-05-07"]
for L, tk in sorted(k.items()):
    i = night[night.ticker == tk].index[0]
    lines.append(f"  2020-05-07 {L} {tk:5s} {'SETUP' if L in 'DKL' else 'no   '} vs 50-day {vs50[i]:+.1%} -> {'kept' if (vs50[i] >= th and vs21[i] >= th21) else 'removed'}")
print("\n".join(lines)); open(f"{HERE}/18_sma50_rule.txt", "w").write("\n".join(lines) + "\n")

# The 4th-smallest limit (+0.65%) drops APT (his 'good' pick, +0.4%) and MDB (a big winner, +0.3%): the plain line, close at or
# above the 50-day SMA, is taken instead — it keeps every QM buy and all three of his picks.
NEW = CUR & (vs50 >= 0.0)
n = NEW.groupby(F.scan_date).sum(); kept = NEW.loc[Q.row].values
extra = [f"\nPLAIN LINE close >= 50-day SMA: his buys {int(kept.sum())}/269 | big winners {int(kept[Q.big.values].sum())}/26 | "
         f"names a night median {n.median():.0f} mean {n.mean():.0f} p90 {n.quantile(.9):.0f}; QM buys dropped "
         f"{int((CUR.loc[Q.row].values & ~(vs50 >= 0).loc[Q.row].values).sum())}; 2020-05-07 his picks kept: "
         + ", ".join(f"{L} {tk} {'kept' if NEW[night[night.ticker == tk].index[0]] else 'removed'}" for L, tk in sorted(k.items()))]
print("\n".join(extra)); open(f"{HERE}/18_sma50_rule.txt", "a").write("\n".join(extra) + "\n")
