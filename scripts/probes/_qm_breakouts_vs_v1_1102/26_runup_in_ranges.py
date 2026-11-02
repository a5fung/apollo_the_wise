#!/usr/bin/env python3
"""His question (11-02): 'On PFE, is it a low adr stock? For low adr, a big run up means different than high adr.' The 6-month
move measured in the stock's own daily ranges (move126 / ADR20 at D), on every label he has given (era A rows): his blind picks
vs rejects, and his labels on QM's buys (good/ok vs no). Then the lines that keep all his ok-or-better, and what they cut."""
import json, os, runpy
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
g = runpy.run_path(f"{HERE}/23_move126_rule.py", run_name="lib")
F, Q, CUR, P, N, qrows, qbig = g["F"], g["Q"], g["CUR"], g["P"], g["N"], g["qrows"], g["qbig"]
F = F.assign(mr=F.move126 / F.adr20)
row = lambda s, e: Q.row[(Q.sym == s) & (Q.E == e)].iloc[0]
lab = pd.read_csv(f"{HERE}/24_move70_labels.tsv", sep="\t")
QL = [(r.sym, r.E, r.his) for r in lab.itertuples()]
QL += [("EW", "2019-08-16", "good"), ("LRN", "2020-08-05", "good"), ("YPF", "2019-04-17", "no"), ("W", "2020-04-07", "no (maybe EP)"),
       ("DOCU", "2020-12-04", "no"), ("DOCU", "2020-12-15", "no"), ("SQM", "2021-09-10", "no"), ("MRNA", "2021-11-29", "no"),
       ("CODX", "2020-04-06", "good"), ("AVLR", "2020-07-29", "likely no"), ("SE", "2020-09-14", "no"), ("AMC", "2021-02-22", "ok"),
       ("DKNG", "2021-02-26", "decent"), ("BNTX", "2021-09-23", "good"), ("LAC", "2021-09-30", "okish"), ("MARA", "2021-11-30", "good")]
T = []
for s, e, h in QL:
    i = row(s, e)
    if i in F.index and pd.notna(F.move126.get(i)):
        T.append(("QM buy", s, e, h, F.move126[i], F.adr20[i], F.mr[i], i))
for i in P: T.append(("his pick", F.ticker[i], F.scan_date[i], "pick", F.move126[i], F.adr20[i], F.mr[i], i))
for i in N: T.append(("his reject", F.ticker[i], F.scan_date[i], "no", F.move126[i], F.adr20[i], F.mr[i], i))
T = pd.DataFrame(T, columns=["who", "sym", "date", "label", "move", "adr", "move_in_ranges", "i"]).drop_duplicates(["sym", "date"])
T["yes"] = ~T.label.str.startswith(("no", "likely no", "looks more like EP"))
out = [T.sort_values("move_in_ranges", ascending=False)[["who", "sym", "date", "label", "move", "adr", "move_in_ranges"]]
       .to_string(index=False, float_format=lambda x: f"{x:.3g}")]
lo_yes = T[T.yes].move_in_ranges.min()
out.append(f"\nlowest ok-or-better: {T[T.yes].sort_values('move_in_ranges').iloc[0][['sym','date','move_in_ranges']].tolist()}")
for th in sorted({round(lo_yes, 2), 8, 10, 12}):
    keep = F.mr >= th - 1e-9
    n = (CUR & keep).groupby(F.scan_date).sum()
    yes, no = T[T.yes], T[~T.yes]
    out.append(f"move >= {th:g} daily ranges: his yes kept {int((yes.move_in_ranges >= th - 1e-9).sum())}/{len(yes)} | his no removed {int((no.move_in_ranges < th - 1e-9).sum())}/{len(no)} | "
               f"QM buys kept {int(keep.loc[qrows].sum())}/{len(qrows)} | big {int(keep.loc[qbig].sum())}/{len(qbig)} | names a night median {n.median():.0f}")
bigdrop = [(Q.sym[Q.row == r].iloc[0], Q.E[Q.row == r].iloc[0], round(float(F.mr[r]), 1)) for r in qbig if F.mr[r] < 12]
out.append(f"big winners under 12 ranges: {bigdrop}")
print("\n".join(out)); open(f"{HERE}/26_runup_in_ranges.txt", "w").write("\n".join(out) + "\n")
