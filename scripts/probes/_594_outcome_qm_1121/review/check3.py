"""PRE-REG 7 sensitivity: KOLD 2022-04-19 scored on its era-A twin (dmin -10.35). Build reading otherwise (excl his-vs-his)."""
import numpy as np, pandas as pd
X = pd.read_csv("scripts/probes/_594_outcome_qm_1121/build/events_scored.tsv.gz", sep="\t", keep_default_na=False, na_values={"dmin": [""]})
X["h"] = X.is_his_buy.astype(str) == "True"
X.loc[(X.era == "A") & (X.ticker == "KOLD") & (X.E == "2022-04-19"), "h"] = True
B7 = X[X.dmin.notna()]
days = [(g.dmin.values, g.h.values) for (e, E), g in B7.groupby(["era", "E"]) if g.h.any() and (~g.h).any()]
print("KOLD day others:", len(B7[(B7.era == "A") & (B7.E == "2022-04-19")]) - 1)
def stat(L):
    s = n = 0.0
    for (d, _), h in zip(days, L):
        a, b = d[h], d[~h]; s += (a[:, None] > b[None, :]).sum() + 0.5 * (a[:, None] == b[None, :]).sum(); n += a.size * b.size
    return s / n, n
P, n = stat([h for _, h in days]); rg = np.random.default_rng(1121)
ge = sum(stat([h[rg.permutation(len(h))] for _, h in days])[0] >= P for _ in range(2000))
print(f"days {len(days)} P {P:.3f} pairs {int(n)} p {(1+ge)/2001:.4f}")
