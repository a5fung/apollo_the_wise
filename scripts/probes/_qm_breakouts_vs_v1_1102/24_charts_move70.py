#!/usr/bin/env python3
"""The 23 of Qullamaggie's buys (era A, on the current list) whose 6-month move is under 70% — the line that keeps all 10 of
his picks and removes 13 of his 24 rejects (list 154 -> 68 a night). Sorted by the move, highest first, so the line his labels
support can be read off. Charts up to QM's buy day (arrow)."""
import os, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from _chartlib import sheet  # noqa
d = pd.read_csv(f"{HERE}/23_move126_drops70.tsv", sep="\t").sort_values("move126", ascending=False).reset_index(drop=True)
items = [(r.ticker, r.E, r.E, f"{chr(65 + i) if i < 26 else i}. {r.sym}  ·  his buy {r.E}{'  ·  BIG WINNER' if r.big else ''}\n6-month move {r.move126:.0%}") for i, r in d.iterrows()]
sheet(items[:12], f"{HERE}/charts/move70_drops_1.png", "Qullamaggie's buys with a 6-month move under 70% (1 of 2) — chart up to his buy day")
sheet(items[12:], f"{HERE}/charts/move70_drops_2.png", "Qullamaggie's buys with a 6-month move under 70% (2 of 2) — chart up to his buy day")
print(len(items))
