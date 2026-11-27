"""Settle the keep-rule boundaries from the prereg's own indicative numbers, using ONLY the 11-13 capture's ci/ticker/fire columns."""
import itertools, json
import numpy as np, pandas as pd
from datetime import date
import r4_keep as K

CAP = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
df = pd.read_parquet(CAP, columns=["ci", "ticker", "fire"])
cal = [date.fromisoformat(x) for x in open(CAP + ".cal.txt").read().split()]
print("rows", len(df), "fire", int(df.fire.sum()), "nights", df.ci.nunique(), "median per night", float(df.groupby("ci").size().median()))
b = df[df.fire].reset_index(drop=True)
idents = b.ticker.to_numpy(); ci = b.ci.to_numpy(); dstr = np.array([cal[c].isoformat() for c in ci])
eyear = np.array([cal[c + 1].year for c in ci])
print("break rows", len(b), "tickers", len(set(idents)))
targets = {1: 15312, 1 / 3: 12384, 1 / 5: 10514, 1 / 8: 8621}
res = {}
for byteorder, incl, (quiet, strict) in itertools.product(["big", "little"], [False, True], [(10, False), (10, True), (9, False)]):
    fq = K.first_after_quiet(idents, ci, quiet, strict)
    row = [f"{byteorder:6s} incl={incl!s:5s} quiet={quiet}/{'strict' if strict else 'ge'} brk_first={fq.mean():.3%}"]
    coins = np.array([K.coin(1124, idents[i], dstr[i], byteorder) for i in range(len(b))])
    for q, t in targets.items():
        k = K.walk(idents, ci, dstr, q, 1124, 60, incl, byteorder, coins)
        row.append(f"q={q:.3f}: n={int(k.sum())} (want {t}) first={fq[k].mean():.0%}")
    print(" | ".join(row), flush=True)
