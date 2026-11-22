"""t_01b: OUTCOME-BLIND. From the saved turn lists only: (1) reproduce the doc's chance shares (pins the inclusive +/-21 code);
(2) edge facts needed to fix the readings before any outcome is opened. No price / VIX / breadth / event file is opened."""
import pandas as pd, numpy as np, hashlib
from t_00_lib import *
print("whole prereg doc sha256 (working tree, §13.1 is NOT committed at run time):", hashlib.sha256(open("../../../docs/analysis/liquidity_composite_prereg_2026-11-22.md", "rb").read()).hexdigest())
grid = pd.read_csv(f"{O}/legs_votes.csv", index_col=0, parse_dates=True).index; vs, ve = grid.get_loc(VS), grid.get_loc(VE); n = ve - vs + 1
LASTLOW = len(grid) - 1 - 63
print(f"vs={vs} ve={ve} n={n}; last session that can hold a 63-session low/high: pos {LASTLOW} = {grid[LASTLOW].date()}; first: pos 63 = {grid[63].date()}")
DOC = {("PRIMARY", "easing"): 52.3, ("PRIMARY", "tightening"): 52.4, ("ALTERNATE", "easing"): 73.5, ("ALTERNATE", "tightening"): 71.8}
cov = lambda d: (pd.Timestamp("2017-03-01") <= d <= pd.Timestamp("2021-12-31")) or (pd.Timestamp("2022-03-31") <= d <= pd.Timestamp("2024-09-30"))
for nm in ("PRIMARY", "ALTERNATE"):
    t = pd.read_csv(f"build_t/turns_{nm}.csv", parse_dates=["date"]); t = t[t.in_window]
    for d in ("easing", "tightening"):
        p = t.pos[t.dir == d].values; w = np.arange(vs, ve + 1); near = (np.abs(w[:, None] - p[None, :]) <= 21).any(axis=1)
        print(f"{nm} {d}: {near.mean()*100:.1f}% of {n} window sessions within +/-21 of a turn | doc {DOC[(nm, d)]} -> {'MATCH' if round(near.mean()*100, 1) == DOC[(nm, d)] else 'MISMATCH'}")
    print(f"  {nm}: turns whose +21 reach passes pos {LASTLOW} (edge-censored in Q1/Q2): {[(str(x.date()), y) for x, y, q in zip(t.date, t.dir, t.pos) if q + 21 > LASTLOW]}")
    print(f"  {nm}: turns whose 20-session window ends after 2024-09-30 (EP and breakout drop): {[(str(x.date()), y) for x, y, q in zip(t.date, t.dir, t.pos) if grid[q + 20] > pd.Timestamp('2024-09-30')]}")
    print(f"  {nm}: turns whose 20-session window touches a session the breakout files do not cover (before 2017-03-01, or 2022-01-01 -> 2022-03-30): {[(str(x.date()), y) for x, y, q in zip(t.date, t.dir, t.pos) if not all(cov(grid[j]) for j in range(q + 1, q + 21)) and grid[q + 20] <= pd.Timestamp('2024-09-30')]}")
