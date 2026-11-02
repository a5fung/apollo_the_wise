#!/usr/bin/env python3
"""The 9 of Qullamaggie's breakout buys the close-vs-EMA21 rule drops (15_ema21_rule.txt): charts up to his buy day (arrow),
for his review (his 11-02 method: gaps go to his eye)."""
import os, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from _chartlib import sheet  # noqa
d = pd.read_csv(f"{HERE}/15_ema21_drops.tsv", sep="\t").sort_values("E")
items = [(r.ticker, r.E, r.E, f"{r.sym}  ·  his buy {r.E} (arrow)\n{abs(r.vs21):.2f} daily ranges under the 21-day EMA (limit 0.27)") for r in d.itertuples()]
sheet(items, f"{HERE}/charts/ema21_drops_9.png", "Qullamaggie's buys the '21-day EMA' rule would drop (chart up to his buy day)")
