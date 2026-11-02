#!/usr/bin/env python3
"""The 6-month move (biggest low -> later high gain inside the 126 sessions before D, the low <= 63 sessions before the high;
bars <= D) for EVERY row of the era-A table (nights to 2022-03-31; era B needs the sealed store's bars and is left for the
freeze). Rule lines 50/60/70/80%: QM's buys kept, big winners, his 10 picks kept, his 24 rejects removed, names a night.
Captured once to apollo_data; no returns read."""
import json, os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/18_sma50_rule.py", run_name="lib")
F, Q, NEW = g["F"], g["Q"], g["NEW"]
from _chartlib import D as DD, runner  # noqa
OUT = "/Users/alvinfung/apollo_data/qm_breakouts_1102/move126_eraA.parquet"
A = F[F.scan_date <= "2022-03-31"]
if not os.path.exists(OUT):
    parts = []
    for tk, grp in A.groupby("ticker"):
        b, _ = runner.bars_for(DD, DD.tid[tk])
        h = pd.Series(np.asarray(b.h, float)); l = pd.Series(np.asarray(b.l, float))
        ratio = h / l.rolling(64, min_periods=1).min() - 1
        m126 = ratio.rolling(126, min_periods=1).max()
        pos = {d.isoformat(): i for i, d in enumerate(b.dates)}
        parts.append(pd.DataFrame({"idx": grp.index, "move126": m126.values[[pos[d] for d in grp.scan_date]]}))
    pd.concat(parts).to_parquet(OUT, index=False)
mv = pd.read_parquet(OUT).set_index("idx").move126
F = F.assign(move126=mv)                                     # NaN outside era A
CUR = NEW & F.move126.notna()
lab = []
for f_, picks in (("sample_night_KEY.json", "DKL"), ("sample_night2_KEY.json", "ADG"), ("sample_night3_KEY.json", "CDFG")):
    k = json.load(open(f"{HERE}/charts/{f_}"))
    for L, tk in k["key"].items():
        if tk == k["his_buy"] and L not in picks:
            continue
        lab.append((F[(F.scan_date == k["night"]) & (F.ticker == tk)].index[0], L in picks))
P = [i for i, p in lab if p]; N = [i for i, p in lab if not p]
qa = Q[(Q.D <= "2022-03-31")]
qrows = qa.row[NEW.loc[qa.row].values].astype(int)
qbig = qa.row[qa.big & NEW.loc[qa.row].values].astype(int)
out = [f"era A: QM buys on the current list {len(qrows)}, big winners {len(qbig)}; his picks {len(P)}, rejects {len(N)}; "
       f"current list median {CUR.groupby(F.scan_date).sum().median():.0f} names a night"]
for th in (0.5, 0.6, 0.7, 0.8):
    keep = F.move126 >= th
    n = (CUR & keep).groupby(F.scan_date).sum()
    out.append(f"6-month move >= {th:.0%}: QM buys kept {int(keep.loc[qrows].sum())}/{len(qrows)} | big winners {int(keep.loc[qbig].sum())}/{len(qbig)} | "
               f"his picks {int(keep.loc[P].sum())}/{len(P)} | his rejects removed {int((~keep.loc[N]).sum())}/{len(N)} | names a night median {n.median():.0f} mean {n.mean():.0f}")
dr = qa[NEW.loc[qa.row].values & (F.move126.loc[qa.row] < 0.7).values]
out.append("QM buys under 70%: " + ", ".join(f"{r.sym} {r.E} {F.move126[r.row]:.0%}{' BIG' if r.big else ''}" for r in dr.sort_values('E').itertuples()))
print("\n".join(out)); open(f"{HERE}/23_move126_rule.txt", "w").write("\n".join(out) + "\n")
dr.assign(move126=F.move126.loc[dr.row].values)[["eid", "sym", "ticker", "D", "E", "move126", "big"]].to_csv(f"{HERE}/23_move126_drops70.tsv", sep="\t", index=False)

# Lower lines (EW, his GOOD label, sits at 42%) and the move measured in daily ranges (move / ADR20).
GOODS = [Q.row[(Q.sym == s) & (Q.E == e)].iloc[0] for s, e in (("EW", "2019-08-16"), ("LRN", "2020-08-05"))]
GOODS += [Q.row[(Q.sym == s) & (Q.E == e)].iloc[0] for s, e in (("CODX", "2020-04-06"), ("BNTX", "2021-09-23"), ("MARA", "2021-11-30"), ("DKNG", "2021-02-26"), ("AMC", "2021-02-22"), ("TSLA", "2022-04-21"), ("LAC", "2021-09-30"))
          if Q.row[(Q.sym == s) & (Q.E == e)].iloc[0] in F.index and F.move126.notna()[Q.row[(Q.sym == s) & (Q.E == e)].iloc[0]]]
more = [f"\nhis ok-or-better labelled QM buys in era A checked too: {len(GOODS)}"]
ma = F.move126 / F.adr20
for name, keep in [(f"6-month move >= {t:.0%}", F.move126 >= t) for t in (0.35, 0.40, 0.42)] + \
                  [(f"6-month move >= {t:g} daily ranges", ma >= t) for t in (8, 10, 12, 14)]:
    n = (CUR & keep).groupby(F.scan_date).sum()
    more.append(f"{name:34s}: QM buys kept {int(keep.loc[qrows].sum())}/{len(qrows)} | big {int(keep.loc[qbig].sum())}/{len(qbig)} | his labelled-good QM buys {int(keep.loc[GOODS].sum())}/{len(GOODS)} | "
                f"his picks {int(keep.loc[P].sum())}/{len(P)} | rejects removed {int((~keep.loc[N]).sum())}/{len(N)} | names a night median {n.median():.0f}")
print("\n".join(more)); open(f"{HERE}/23_move126_rule.txt", "a").write("\n".join(more) + "\n")
