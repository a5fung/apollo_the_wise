#!/usr/bin/env python3
"""Volume measured against the last 10 sessions (the base) instead of the 50-day average: breakouts a day on the rebuilt list
and QM's buys firing on his day. Same price test (high above the 5-day high). Era A, current rules; no returns."""
import os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/34_trigger_day.py", run_name="lib")
F, Q, CUR, q = g["F"], g["Q"], g["CUR"], g["q"]
from _chartlib import D as DD, runner  # noqa
OUT = "/Users/alvinfung/apollo_data/qm_breakouts_1102/trigger_v10_eraA.parquet"
if not os.path.exists(OUT):
    parts = []
    for tk, grp in F[(F.scan_date <= "2022-03-31") & CUR].groupby("ticker"):
        b, _ = runner.bars_for(DD, DD.tid[tk])
        h, v = pd.Series(np.asarray(b.h, float)), pd.Series(np.asarray(b.v, float))
        lvl = h.rolling(5).max(); up = h.shift(-1) > lvl
        pos = {d.isoformat(): i for i, d in enumerate(b.dates)}; ii = [pos[d] for d in grp.scan_date]
        nxt = [b.dates[i + 1].isoformat() if i + 1 < len(b.dates) else None for i in ii]
        parts.append(pd.DataFrame({"idx": grp.index, "up": up.values[ii], "x10": (v.shift(-1) / v.rolling(10).mean()).values[ii],
                                   "x50": (v.shift(-1) / v.rolling(50).mean()).values[ii], "E_bar": nxt}))
    pd.concat(parts).to_parquet(OUT, index=False)
T = pd.read_parquet(OUT).set_index("idx")
T = T[T.E_bar.values == F.E.reindex(T.index).values]
nights = F.scan_date[F.scan_date <= "2022-03-31"].unique()
out = []
for name, m in (("price only (no volume rule)", T.up), ("volume >= 1.2x the 50-day (v1 today)", T.up & (T.x50 >= 1.2)),
                ("volume >= 1.2x the last 10 days", T.up & (T.x10 >= 1.2)), ("volume >= 1.5x the last 10 days", T.up & (T.x10 >= 1.5))):
    per = m.groupby(F.scan_date.reindex(m.index)).sum().reindex(nights, fill_value=0)
    qi = q.row.astype(int); hit = m.reindex(qi).fillna(False).values
    out.append(f"{name:40s} breakouts a day: median {per.median():.0f}, mean {per.mean():.1f} | QM buys firing on his day {int(hit.sum())}/{len(q)} | big {int(hit[q.big.values].sum())}/{int(q.big.sum())}")
print("\n".join(out)); open(f"{HERE}/36_trigger_vol10.txt", "w").write("\n".join(out) + "\n")
