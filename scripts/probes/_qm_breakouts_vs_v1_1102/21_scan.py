#!/usr/bin/env python3
"""His blind picks on 3 sample nights (10 picks, 24 not picked; QM's own unpicked buys NVDA/LCID excluded from both) vs every
measure in the table. For each measure and direction: the loosest line that keeps ALL 10 picks; then how many of the 24 it
removes, how many of QM's 263 kept buys it drops (those would go to him as charts), and names a night on top of the current
list. Exploratory; no returns read."""
import json, os, runpy
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
g = runpy.run_path(f"{HERE}/18_sma50_rule.py", run_name="lib")
F, Q, NEW = g["F"], g["Q"], g["NEW"]
want = ["adr20", "rs_best", "prior_move", "close", "e10", "e21", "hi252", "e21_rise_base", "prior_move.base_len", "prior_move.pole_high",
        "prior_move.pole_low", "higher_lows.base_low", "higher_lows.recent_low", "surf.best", "surf.run10", "surf.run20", "surf.run50",
        "tightening.ratio", "tightening.range_early5", "tightening.range_recent5", "universe.dollar_vol20", "universe.raw_close",
        "breakdown.sma10", "breakdown.sma20", "breakdown.sma50", "breakdown.low", "breakdown.prior_low10", "level"]
X = pd.concat([pd.read_parquet(f"/Users/alvinfung/apollo_data/qm_breakouts_1102/features_era{e}.parquet", columns=[c for c in want if c not in ("adr20", "rs_best", "prior_move", "close", "e21")]) for e in "AB"], ignore_index=True)
for c in ("adr20", "rs_best", "prior_move", "close", "e21"):
    X[c] = F[c].values
a = X.adr20
M = pd.DataFrame({
    "strength rank": X.rs_best, "daily range": a, "run-up": X.prior_move, "base length": X["prior_move.base_len"],
    "base depth (ranges)": (X["prior_move.pole_high"] - X["higher_lows.base_low"]) / X["prior_move.pole_high"] / a,
    "below the pole top %": 1 - X.close / X["prior_move.pole_high"], "below 52w high %": 1 - X.close / X.hi252,
    "close vs EMA10 (ranges)": (X.close / X.e10 - 1) / a, "close vs EMA21 (ranges)": (X.close / X.e21 - 1) / a,
    "EMA10 vs EMA21 (ranges)": (X.e10 / X.e21 - 1) / a, "close vs SMA10 %": X.close / X["breakdown.sma10"] - 1,
    "close vs SMA20 %": X.close / X["breakdown.sma20"] - 1, "close vs SMA50 %": X.close / X["breakdown.sma50"] - 1,
    "SMA20 vs SMA50 %": X["breakdown.sma20"] / X["breakdown.sma50"] - 1, "EMA21 rise across base": X.e21_rise_base,
    "tightening ratio": X["tightening.ratio"], "recent 5-day range %": X["tightening.range_recent5"],
    "recent low vs base low (ranges)": (X["higher_lows.recent_low"] / X["higher_lows.base_low"] - 1) / a,
    "close vs base low (ranges)": (X.close / X["higher_lows.base_low"] - 1) / a, "close vs buy level (ranges)": (X.close / X.level - 1) / a,
    "riding count best": X["surf.best"], "riding 10-day": X["surf.run10"], "riding 20-day": X["surf.run20"], "riding 50-day": X["surf.run50"],
    "dollar volume": X["universe.dollar_vol20"], "price": X["universe.raw_close"], "low vs prior 10-day low (ranges)": (X["breakdown.low"] / X["breakdown.prior_low10"] - 1) / a,
}).replace([np.inf, -np.inf], np.nan)
lab = []
for f_, picks in (("sample_night_KEY.json", "DKL"), ("sample_night2_KEY.json", "ADG"), ("sample_night3_KEY.json", "CDFG")):
    k = json.load(open(f"{HERE}/charts/{f_}"))
    for L, tk in k["key"].items():
        if tk == k["his_buy"] and L not in picks:
            continue
        i = F[(F.scan_date == k["night"]) & (F.ticker == tk)].index[0]
        lab.append((i, L in picks, k["night"], tk))
P = [i for i, p, _, _ in lab if p]; N = [i for i, p, _, _ in lab if not p]
qrows = Q.row[NEW.loc[Q.row].values].astype(int).values
base_n = NEW.groupby(F.scan_date).sum().median()
rows = []
for name in M.columns:
    v = M[name]
    for d in (">=", "<="):
        th = v.loc[P].min() if d == ">=" else v.loc[P].max()
        keep = (v >= th) if d == ">=" else (v <= th)
        rem = int((~keep.loc[N]).sum()); qd = int((~keep.loc[qrows]).sum())
        qbig = int((~keep.loc[Q.row[Q.big & NEW.loc[Q.row].values].astype(int)]).sum())
        n = (NEW & keep).groupby(F.scan_date).sum().median()
        rows.append((name, d, th, rem, qd, qbig, n))
R = pd.DataFrame(rows, columns=["measure", "dir", "line (keeps all 10 picks)", "rejects removed /24", "QM buys dropped /263", "QM big winners dropped", "names a night"])
R = R.sort_values(["rejects removed /24", "QM buys dropped /263"], ascending=[False, True])
out = f"current list median {base_n:.0f} names a night; labelled: {len(P)} picks, {len(N)} not picked\n" + R.head(20).to_string(index=False, float_format=lambda x: f"{x:.3g}")
print(out); open(f"{HERE}/21_scan.txt", "w").write(out + "\n")
