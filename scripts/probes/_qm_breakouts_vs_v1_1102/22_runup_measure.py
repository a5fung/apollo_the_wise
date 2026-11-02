#!/usr/bin/env python3
"""The scan's best separator is run-up >= 70% (v1's measure: pole low -> pole top, the pole top searched 10-45 sessions back):
keeps all 10 of his picks, removes 20 of 24 rejects, but 'drops' 109 of QM's buys. Is that QM buying small run-ups, or v1's
measure missing QM's real moves? A second measure, independent of v1's pole: the biggest gain from a low to a later high
inside the 126 sessions before D, the low no more than 63 sessions before the high. Free, local, bars <= D."""
import json, os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
g = runpy.run_path(f"{HERE}/18_sma50_rule.py", run_name="lib")
F, Q, NEW = g["F"], g["Q"], g["NEW"]
from _chartlib import D as DD, runner  # noqa
def move126(tk, d):
    b, _ = runner.bars_for(DD, DD.tid[tk]); dates = [x.isoformat() for x in b.dates]
    i = dates.index(d); h = np.asarray(b.h, float); l = np.asarray(b.l, float); best = 0.0
    for j in range(max(1, i - 125), i + 1):
        lo = l[max(0, j - 63):j + 1].min(); best = max(best, h[j] / lo - 1)
    return best
pm = F.prior_move
rows = []
kept = Q[NEW.loc[Q.row].values & (Q.D <= "2022-06-29")]
for r in kept.itertuples():
    rows.append(("QM buy", r.sym, r.D, float(pm[r.row]), move126(r.ticker, r.D), bool(r.big)))
lab = []
for f_, picks in (("sample_night_KEY.json", "DKL"), ("sample_night2_KEY.json", "ADG"), ("sample_night3_KEY.json", "CDFG")):
    k = json.load(open(f"{HERE}/charts/{f_}"))
    for L, tk in k["key"].items():
        if tk == k["his_buy"] and L not in picks:
            continue
        i = F[(F.scan_date == k["night"]) & (F.ticker == tk)].index[0]
        rows.append(("his PICK" if L in picks else "his no", tk, k["night"], float(pm[i]), move126(tk, k["night"]), False))
T = pd.DataFrame(rows, columns=["who", "sym", "D", "runup_v1", "move126", "big"])
T.to_csv(f"{HERE}/22_runup_measure.tsv", sep="\t", index=False)
out = []
for who in ("QM buy", "his PICK", "his no"):
    s = T[T.who == who]
    out.append(f"{who:8s} n {len(s):3d} | v1 run-up >= 70%: {int((s.runup_v1 >= .7).sum()):3d} | 6-month move >= 70%: {int((s.move126 >= .7).sum()):3d} | >= 100%: {int((s.move126 >= 1).sum()):3d}")
s = T[(T.who == "QM buy") & (T.runup_v1 < .7)]
out.append(f"QM buys under 70% on v1's measure: {len(s)}; of those, 6-month move >= 70%: {int((s.move126 >= .7).sum())}, >= 50%: {int((s.move126 >= .5).sum())}; big winners among them {int(s.big.sum())}")
out.append("his picks: " + ", ".join(f"{r.sym} v1 {r.runup_v1:.0%} / 6m {r.move126:.0%}" for r in T[T.who == 'his PICK'].itertuples()))
out.append("his no's:  " + ", ".join(f"{r.sym} v1 {r.runup_v1:.0%} / 6m {r.move126:.0%}" for r in T[T.who == 'his no'].itertuples()))
print("\n".join(out)); open(f"{HERE}/22_runup_measure.txt", "w").write("\n".join(out) + "\n")
