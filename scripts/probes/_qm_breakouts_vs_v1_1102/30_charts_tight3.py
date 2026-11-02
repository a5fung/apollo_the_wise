#!/usr/bin/env python3
"""Qullamaggie's buys (era A, on the current list) whose last 10 closes spread MORE than 3 daily ranges — the line his labels
support best (keeps 28 of his 31 yes, removes 14 of 41 no). Loosest first, so the line he accepts can be read off. Charts up to
QM's buy day (arrow); the spread is measured on the night before."""
import os, runpy, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/28_tight_into_breakout.py", run_name="lib")
F, Q, CUR, Tt = g["F"], g["Q"], g["CUR"], g["Tt"]
from _chartlib import sheet  # noqa
qa = Q[(Q.D <= "2022-03-31")].copy()
qa = qa[CUR.reindex(qa.row.astype(int)).values]
qa["c10"] = Tt["close10"].reindex(qa.row.astype(int)).values
d = qa[qa.c10 > 3].sort_values("c10", ascending=False).reset_index(drop=True)
d[["eid", "sym", "ticker", "D", "E", "c10", "big"]].to_csv(f"{HERE}/30_tight3_drops.tsv", sep="\t", index=False)
lab = lambda i: chr(65 + i) if i < 26 else "A" + chr(65 + i - 26)
items = [(r.ticker, r.E, r.E, f"{lab(i)}. {r.sym}  ·  his buy {r.E}{'  ·  BIG WINNER' if r.big else ''}\nlast 10 closes spread {r.c10:.1f} daily ranges") for i, r in d.iterrows()]
for k in range(0, len(items), 12):
    sheet(items[k:k + 12], f"{HERE}/charts/tight3_drops_{k // 12 + 1}.png",
          f"Qullamaggie's buys that were NOT tight into the buy (last 10 closes over 3 daily ranges) — loosest first ({k // 12 + 1} of {(len(items) + 11) // 12})")
print(len(items), int(d.big.sum()))
