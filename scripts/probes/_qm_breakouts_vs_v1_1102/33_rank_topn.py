#!/usr/bin/env python3
"""After round 7 (his labels on the 29 loose QM buys: most rated ok, so tightness alone can't be a cut — separation 0.62 on all
95 labels): RANK each night's list instead. Score = mean of two within-night percentiles: the 6-month run-up in daily ranges
(bigger first) and the last-10-close spread in daily ranges (tighter first). Measured: his yes vs no on the score, and how many
of QM's buys sit in the top 10/20/30/50 of their night. Era A, current rules. No returns."""
import os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/32_tight_recently.py", run_name="lib")
F, Q, CUR, Tt, L, qrows, qbig = g["F"], g["Q"], g["CUR"], g["Tt"], g["L"], g["qrows"], g["qbig"]
A = F[CUR].assign(mr=lambda x: x.move126 / x.adr20, c10=lambda x: Tt.c10.reindex(x.index).values)
A["p_run"] = A.groupby("scan_date").mr.rank(pct=True)                 # 1 = biggest run-up
A["p_tight"] = A.groupby("scan_date").c10.rank(pct=True, ascending=False)   # 1 = tightest
out = []
for name, col in (("run-up only", "p_run"), ("tightness only", "p_tight"), ("run-up + tightness", None)):
    s = A[col] if col else (A.p_run + A.p_tight) / 2
    rank = s.groupby(A.scan_date).rank(ascending=False, method="first")
    yy, nn = [i for i in L[L.yes].i if i in s.index], [i for i in L[~L.yes].i if i in s.index]
    auc = np.mean([[1.0 if s[u] > s[v] else (0.5 if s[u] == s[v] else 0.0) for v in nn] for u in yy])
    qr = rank.reindex(qrows).dropna(); br = rank.reindex(qbig).dropna()
    out.append(f"{name:20s} his yes above his no {auc:.2f} (yes {len(yy)}, no {len(nn)} on the list) | QM buys in their night's top 10: {int((qr <= 10).sum())}, "
               f"top 20: {int((qr <= 20).sum())}, top 30: {int((qr <= 30).sum())}, top 50: {int((qr <= 50).sum())} of {len(qr)} | big winners top 20: {int((br <= 20).sum())}, top 50: {int((br <= 50).sum())} of {len(br)}")
out.append(f"era-A list: median {A.groupby('scan_date').size().median():.0f} names a night")
print("\n".join(out)); open(f"{HERE}/33_rank_topn.txt", "w").write("\n".join(out) + "\n")
