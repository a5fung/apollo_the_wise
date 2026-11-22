"""Sensitivities: KOLD era twin; 95 era-A events dropped near A-file end given B-twin outcomes. Reads build TSV only."""
import numpy as np, pandas as pd
X = pd.read_csv("scripts/probes/_594_outcome_qm_1121/build/events_scored.tsv.gz", sep="\t", keep_default_na=False,
                na_values={k: [""] for k in ("dmin", "tercile", "big_winner", "ret60", "fail5")})
for c in ("is_his_buy", "in_prereg6"): X[c] = X[c].astype(str) == "True"
print(X[X.ticker == "KOLD"][X.E == "2022-04-19"][["era", "ticker", "E", "dmin", "null", "big_winner"]].to_string())
# his buys in overlap: twin rows
ov = X[(X.E >= "2021-09-27") & (X.E <= "2022-06-30")]
for r in X[X.is_his_buy & (X.E >= "2021-09-27") & (X.E <= "2022-06-30")].itertuples():
    print("his overlap", r.era, r.ticker, r.E, r.dmin, "| twins:", ov[(ov.ticker == r.ticker) & (ov.E == r.E) & (ov.era != r.era)][["era", "dmin", "big_winner"]].values.tolist())
# 95 dropped era-A: attach era-B twin outcome
A = X[(X.era == "A") & ~X.in_prereg6]
Bt = X[X.era == "B"].set_index(["ticker", "E"])
add = []
for r in A.itertuples():
    if (r.ticker, r.E) in Bt.index:
        b = Bt.loc[(r.ticker, r.E)]
        if pd.notna(b.big_winner) and pd.notna(r.dmin):
            add.append(dict(era="A", ticker=r.ticker, E=r.E, month=r.month, dmin=r.dmin, big_winner=b.big_winner))
print(f"era-A forward-dropped {len(A)}; with B-twin outcome and A dmin: {len(add)}; big winners among them {sum(a['big_winner'] for a in add)}")
P6 = X[X.in_prereg6][["era", "ticker", "E", "month", "dmin", "big_winner"]]
T = pd.concat([P6, pd.DataFrame(add)], ignore_index=True)
T = T[T.dmin.notna()]
# drop B twins (NULL anyway) — assert no dup scored
assert not T.duplicated(["ticker", "E"]).any()
mc = T.groupby("month").size(); T = T[T.month.isin(mc[mc >= 6].index)].sort_values(["month", "dmin", "ticker"], kind="mergesort").reset_index(drop=True)
terc = np.empty(len(T), int); groups = []
for m in T.month.unique():
    g = np.flatnonzero((T.month == m).values); groups.append(g)
    for k, part in enumerate(np.array_split(g, 3)): terc[part] = k
bw = T.big_winner.values; rat = lambda tc: bw[tc == 2].mean() / bw[tc == 0].mean()
obs = rat(terc); rg = np.random.default_rng(1121); ge = 0
for _ in range(2000):
    tc = np.empty(len(T), int)
    for g in groups: tc[g] = terc[g][rg.permutation(len(g))]
    ge += rat(tc) >= obs
print(f"sensitivity (+ era-A late events scored on B-twin outcome): n {len(T)} ratio {obs:.3f} p {(1+ge)/2001:.4f}")
