"""03: second-route recount of the E3 run lengths (itertools.groupby straight from legs_X.csv, votes rebuilt). Outcome-blind: reads legs_X.csv only."""
import pandas as pd, numpy as np, itertools
X = pd.read_csv("build/legs_X.csv", index_col=0, parse_dates=True); FR = pd.read_csv("build/legs_fresh.csv", index_col=0, parse_dates=True)
H = {"H1": ("2016-03-15", "2020-12-31"), "H2": ("2021-01-04", "2024-12-31")}
print("leg half  runs  median  mean  share_of_runs_1-2_sessions  share_of_runs>=5  longest | recount of 02")
for k in X.columns:
    x = X[k].values; v = []
    for i in range(len(x)):
        if i < 49: v.append(None); continue
        if k in ("C3", "F2", "F3", "R1", "R2"):  # FRED levels quoted in hundredths: exact integer arithmetic, a tie is 0
            xi = [int(round(z * 100)) for z in x[i-49:i+1]]; s20, s50 = sum(xi[-20:]), sum(xi); a, b, c, d = xi[-1] * 20, s20, s20 * 50, s50 * 20
        else:
            import math
            a, b = x[i], math.fsum(x[i-19:i+1]) / 20; c, d = b, math.fsum(x[i-49:i+1]) / 50
            if abs(a - b) <= 1e-9 * max(1, abs(a), abs(b)): a = b
            if abs(c - d) <= 1e-9 * max(1, abs(c), abs(d)): c = d
        v.append(None if not FR[k].iloc[i] else (1 if (a > b and c > d) else (-1 if (a < b and c < d) else 0)))
    s = pd.Series(v, X.index, dtype=object)
    for h, (a, b) in H.items():
        seq = list(s.loc[a:b]); rl = [len(list(g)) for key, g in itertools.groupby(seq) if key is not None]
        rl = np.array(rl); print(f"{k}  {h}  {len(rl):4d}  {np.median(rl):5.1f}  {rl.mean():5.1f}  {(rl<=2).mean()*100:5.1f}%  {(rl>=5).mean()*100:5.1f}%  {rl.max():4d}")
    V2 = pd.read_csv("build/legs_votes.csv", index_col=0, parse_dates=True)[k]
    sv = pd.to_numeric(s, errors="coerce"); m = sv.notna() | V2.notna()
    print(f"      {k}: votes differing from 01's saved votes: {int((sv[m] != V2[m]).sum())} of {int(m.sum())}")
