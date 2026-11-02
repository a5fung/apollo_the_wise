#!/usr/bin/env python3
"""Second BLIND sample night under the current rules (start + base-depth band + 32.1% run-up + close-vs-EMA21 >= TSLA's -0.63 +
close >= 50-day SMA): the night before one of Qullamaggie's big winners whose list size is nearest the current median, outside
the 2020 crash window and not 2020-05-07 (used); his buy + 11 random others (seed 1103), lettered A-L; charts end that night."""
import json, os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/18_sma50_rule.py", run_name="lib")
F, Q, NEW = g["F"], g["Q"], g["NEW"]
from _chartlib import sheet  # noqa
sizes = NEW.groupby(F.scan_date).sum(); med = sizes.median()
big = Q[Q.big & Q.D.isin(sizes.index)].copy(); big["n"] = big.D.map(sizes)
big = big[~big.D.between("2020-02-20", "2020-04-30") & (big.D != "2020-05-07") & (big.D <= "2022-06-29")]   # store A charts
pick = big.iloc[(big.n - med).abs().argsort()].iloc[0]
night = F[NEW & (F.scan_date == pick.D)]
others = night[night.ticker != pick.ticker].sample(11, random_state=1103).ticker.tolist()
names = [pick.ticker] + others
order = np.random.default_rng(1103).permutation(len(names)); letters = "ABCDEFGHIJKL"
key = {letters[i]: names[k] for i, k in enumerate(order)}
json.dump({"night": pick.D, "his_buy": pick.ticker, "his_buy_day": pick.E, "list_size_that_night": int(pick.n),
           "median_list_size": float(med), "key": key}, open(f"{HERE}/charts/sample_night2_KEY.json", "w"), indent=1)
sheet([(key[L], pick.D, None, L) for L in letters], f"{HERE}/charts/sample_night2_blind.png",
      f"Second sample night of the list ({int(pick.n)} names that night): 12 of them, lettered, charts end that night — which are setups?")
print("night", pick.D, "size", int(pick.n), "median", med)
