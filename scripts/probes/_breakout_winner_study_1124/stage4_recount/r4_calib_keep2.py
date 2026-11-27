import numpy as np, pandas as pd
from datetime import date
import r4_keep as K
CAP = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
df = pd.read_parquet(CAP, columns=["ci", "ticker", "fire"])
cal = [date.fromisoformat(x) for x in open(CAP + ".cal.txt").read().split()]
b = df[df.fire].reset_index(drop=True)
idents = b.ticker.to_numpy(); ci = b.ci.to_numpy(); dstr = np.array([cal[c].isoformat() for c in ci])
fq = K.first_after_quiet(idents, ci, 10, False)
base = fq.mean()
print("break-row first share", base)
chosen = None
for q in K.GRID:
    k = K.walk(idents, ci, dstr, q, 1124, 60, True, "big")
    sh = fq[k].mean()
    print(f"q={q:.4f} n={int(k.sum())} first-share={sh:.4f} ratio={sh/base:.3f} ok={sh<=2*base}")
    if chosen is None and sh <= 2 * base: chosen = q
print("chosen q", chosen)
k = K.walk(idents, ci, dstr, chosen, 1124, 60, True, "big")
ey = pd.Series([cal[c+1].year for c in ci[k]]); print(ey.value_counts().sort_index().to_dict(), "tickers", len(set(idents[k])))
em = pd.Series([f"{cal[c+1].year}-{cal[c+1].month:02d}" for c in ci[k]]); print("months", em.nunique(), "smallest", em.value_counts().min())
k2 = K.walk(idents, ci, dstr, chosen, 2411, 60, True, "big")
print("seed2411 n", int(k2.sum()), "common", int((k & k2).sum()))
