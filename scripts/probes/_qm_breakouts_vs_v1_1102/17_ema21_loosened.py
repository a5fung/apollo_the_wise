#!/usr/bin/env python3
"""After his labels on the 9 EMA21 drops (7 rated ok or better, incl. TSLA 'ok' at -0.63 and MARA 'good' at -0.58): the
close-vs-EMA21 limit loosened to keep every buy he rated ok or better -> the lowest of those (TSLA). Counts and the 2020-05-07
sample night. No returns read."""
import json, os, runpy
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
g = runpy.run_path(f"{HERE}/15_ema21_rule.py", run_name="lib")      # reuses its frames (prints its own table first)
F, Q, AFTER, vs21 = g["F"], g["Q"], g["AFTER"], g["vs21"]
d = pd.read_csv(f"{HERE}/15_ema21_drops.tsv", sep="\t")
th = float(d.loc[d.sym == "TSLA", "vs21"].iloc[0])
lines = [f"\nloosened limit = TSLA's value (lowest of his ok-or-better): {th:.4f} daily ranges"]
for name, m in (("after his labels (no EMA21 rule)", AFTER), ("+ EMA21 rule at -0.27 (first try)", AFTER & (vs21 >= g["th"])),
                ("+ EMA21 rule loosened to his labels", AFTER & (vs21 >= th))):
    n = m.groupby(F.scan_date).sum(); kept = m.loc[Q.row].values
    lines.append(f"{name:40s} his buys {int(kept.sum())}/269 | big winners {int(kept[Q.big.values].sum())}/26 | names a night median {n.median():.0f} mean {n.mean():.0f} p90 {n.quantile(.9):.0f}")
still = Q[AFTER.loc[Q.row].values & ~(vs21 >= th).loc[Q.row].values]
lines.append(f"QM buys still dropped by the loosened rule: {len(still)} " + ", ".join(f"{r.sym} {r.E}" for r in still.itertuples()))
k = json.load(open(f"{HERE}/charts/sample_night_KEY.json"))["key"]
night = F[F.scan_date == "2020-05-07"]
for L, tk in sorted(k.items()):
    r = night[night.ticker == tk]
    v = float(vs21.loc[r.index[0]])
    lines.append(f"  2020-05-07 {L} {tk:5s} {'SETUP' if L in 'DKL' else 'no   '} close vs EMA21 {v:+.2f} -> {'kept' if v >= th else 'removed'}")
print("\n".join(lines)); open(f"{HERE}/17_ema21_loosened.txt", "w").write("\n".join(lines) + "\n")
