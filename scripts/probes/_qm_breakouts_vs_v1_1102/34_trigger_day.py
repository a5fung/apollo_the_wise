#!/usr/bin/env python3
"""His 'ok' (11-02): narrow at the BUY. v1's own daily breakout test (breakout_v1.breakout_triggered): on E = the next session,
high > the list level (highest high of the 5 sessions to D) AND volume >= 1.2 x the 50-session average to D. On the rebuilt list
(era A, current rules): how many names trigger a day; whether QM's buys trigger on his buy day, or on an earlier day within the
5 sessions before it (his 'buy point a few days earlier'); his labels' trigger rates. The E bar is the entry event itself, not an
outcome; no returns read."""
import os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/32_tight_recently.py", run_name="lib")
F, Q, CUR, L, qrows, qbig = g["F"], g["Q"], g["CUR"], g["L"], g["qrows"], g["qbig"]
from _chartlib import D as DD, runner  # noqa
OUT = "/Users/alvinfung/apollo_data/qm_breakouts_1102/trigger_eraA.parquet"
if not os.path.exists(OUT):
    parts = []
    for tk, grp in F[F.scan_date <= "2022-03-31"].groupby("ticker"):
        b, _ = runner.bars_for(DD, DD.tid[tk])
        h, v = pd.Series(np.asarray(b.h, float)), pd.Series(np.asarray(b.v, float))
        lvl = h.rolling(5).max(); v50 = v.rolling(50).mean()
        fired = (h.shift(-1) > lvl) & (v.shift(-1) >= 1.2 * v50)          # E = the next stored session
        pos = {d.isoformat(): i for i, d in enumerate(b.dates)}; ii = [pos[d] for d in grp.scan_date]
        nxt = [b.dates[i + 1].isoformat() if i + 1 < len(b.dates) else None for i in ii]
        parts.append(pd.DataFrame({"idx": grp.index, "fired": fired.values[ii], "E_bar": nxt}))
    pd.concat(parts).to_parquet(OUT, index=False)
T = pd.read_parquet(OUT).set_index("idx")
F = F.assign(E=pd.concat([pd.read_parquet(f"/Users/alvinfung/apollo_data/qm_breakouts_1102/features_era{e}.parquet", columns=["E"]) for e in "AB"], ignore_index=True)["E"].values)
fired = T.fired.reindex(F.index).fillna(False).astype(bool) & (T.E_bar.reindex(F.index) == F.E)   # a hole after D is not a trigger
eraA = F.scan_date <= "2022-03-31"; nights = F.scan_date[eraA].unique()
per = (CUR & fired)[eraA].groupby(F.scan_date[eraA]).sum().reindex(nights, fill_value=0)
lst = CUR[eraA].groupby(F.scan_date[eraA]).sum().reindex(nights, fill_value=0)
out = [f"era-A nights {len(nights)}: list median {lst.median():.0f} a night -> breakouts the next day: median {per.median():.0f}, mean {per.mean():.1f}, "
       f"90th pct {per.quantile(.9):.0f}; days with 0: {int((per == 0).sum())}, with more than 5: {int((per > 5).sum())} ({(per > 5).mean():.0%})"]
q = Q[(Q.D <= "2022-03-31")].copy(); q = q[CUR.reindex(q.row.astype(int)).values]
q["fired_E"] = fired.reindex(q.row.astype(int)).values
# earlier: did the same stock trigger from the list on any of the 5 nights before QM's night D?
key = {(t, d): i for i, t, d in zip(F.index, F.ticker, F.scan_date)}
cal = sorted(F.scan_date.unique()); cpos = {d: i for i, d in enumerate(cal)}
def earlier(tk, d):
    for k in range(1, 6):
        j = cpos[d] - k
        if j < 0: break
        i = key.get((tk, cal[j]))
        if i is not None and CUR[i] and fired[i]: return cal[j]
    return None
q["earlier"] = [earlier(t, d) for t, d in zip(q.ticker, q.D)]
out.append(f"QM's {len(q)} era-A buys on the list: broke out on HIS buy day {int(q.fired_E.sum())} | not on his day but in the 5 days before {int((~q.fired_E & q.earlier.notna()).sum())} | "
           f"neither {int((~q.fired_E & q.earlier.isna()).sum())}")
qb = q[q.big]
out.append(f"  big winners ({len(qb)}): on his day {int(qb.fired_E.sum())} | earlier {int((~qb.fired_E & qb.earlier.notna()).sum())} | neither {int((~qb.fired_E & qb.earlier.isna()).sum())}")
nf = q[~q.fired_E & q.earlier.isna()]
out.append("  neither (no breakout by this test on his day or the 5 before): " + ", ".join(f"{r.sym} {r.E}{' BIG' if r.big else ''}" for r in nf.sort_values('E').itertuples()))
yy = [i for i in L[L.yes].i if i in F.index and CUR[i]]; nn = [i for i in L[~L.yes].i if i in F.index and CUR[i]]
out.append(f"his labels on the list: yes broke out next day {int(fired[yy].sum())}/{len(yy)} | no {int(fired[nn].sum())}/{len(nn)}")
q[["eid", "sym", "ticker", "D", "E", "big", "fired_E", "earlier"]].to_csv(f"{HERE}/34_trigger_qm.tsv", sep="\t", index=False)
print("\n".join(out)); open(f"{HERE}/34_trigger_day.txt", "w").write("\n".join(out) + "\n")
