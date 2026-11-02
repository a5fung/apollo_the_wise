#!/usr/bin/env python3
"""CORRECTION (11-02): 23_/26_/28_ computed 'names a night' with groupby over ALL nights, so the 690 era-B nights (no 6-month
move computed -> 0 rows) pulled the median down (reported 154 / 143 / 68 / 151 were too low). Recount on era-A nights only."""
import os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/28_tight_into_breakout.py", run_name="lib")
F, CUR, Tt, qrows, qbig = g["F"], g["CUR"], g["Tt"], g["qrows"], g["qbig"]
eraA = F.scan_date <= "2022-03-31"
nights = F.scan_date[eraA].unique()
def size(m):
    s = m[eraA].groupby(F.scan_date[eraA]).sum().reindex(nights, fill_value=0)
    return f"median {s.median():.0f}, mean {s.mean():.0f}"
mr = F.move126 / F.adr20
c10 = Tt["close10"].reindex(F.index)
out = [f"era-A nights {len(nights)}; current list (start + depth band + 32% pole run-up + EMA21 >= -0.63 + close >= SMA50): {size(CUR)}"]
for th in (0.4, 0.5, 0.7): out.append(f"  + 6-month move >= {th:.0%}: {size(CUR & (F.move126 >= th))}")
for th in (8, 10, 12): out.append(f"  + 6-month move >= {th} daily ranges: {size(CUR & (mr >= th))}")
for th in (3, 3.5, 4, 5): out.append(f"  + last 10 closes within {th} daily ranges: {size(CUR & (c10 <= th))}")
out.append(f"  + 8 daily ranges run-up AND last 10 within 4: {size(CUR & (mr >= 8) & (c10 <= 4))}")
print("\n".join(out)); open(f"{HERE}/29_recount_era_a.txt", "w").write("\n".join(out) + "\n")
