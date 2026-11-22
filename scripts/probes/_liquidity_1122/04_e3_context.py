"""04: outcome-blind context for the E3 result (information only, NOT a re-selection): which gate each leg fails, and the median length of TIGHT/EASY runs alone."""
import pandas as pd, numpy as np
V = pd.read_csv("build/legs_votes.csv", index_col=0, parse_dates=True)
H = {"H1": ("2016-03-15", "2020-12-31"), "H2": ("2021-01-04", "2024-12-31")}
print("leg  median run all three states (H1,H2) | median run of tight/easy runs only (H1,H2) | median run of flat runs (H1,H2)")
for k in V.columns:
    o = []
    for h, (a, b) in H.items():
        v = V.loc[a:b, k].dropna(); r = v.groupby((v != v.shift()).cumsum()).agg(["first", "size"])
        o.append((r["size"].median(), r.loc[r["first"] != 0, "size"].median(), r.loc[r["first"] == 0, "size"].median()))
    print(f"{k}   {o[0][0]:4.1f} {o[1][0]:4.1f} | {o[0][1]:4.1f} {o[1][1]:4.1f} | {o[0][2]:4.1f} {o[1][2]:4.1f}")
