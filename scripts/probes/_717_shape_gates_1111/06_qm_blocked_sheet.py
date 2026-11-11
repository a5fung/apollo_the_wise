#!/usr/bin/env python3
"""Round 2 diagnosis sheet: 12 of Qullamaggie's listed buys that the FIRST set's structure gates block — 4 that fail
`higher_lows`, 4 `no_lower_low`, 4 `rising_avg` (drawn at random within each, seed 1111, no repeats). Outcome-blind:
each chart ENDS THE NIGHT BEFORE his buy (the buy day is cut off before drawing); no ticker or date shown. Dashed black
= the list's level (the 5-day high). Diagnosis marks: grey dotted vertical = the pole top the list found (the base
starts after it); orange dotted vertical = the base's lowest low. EMA10 blue, EMA21 red, SMA50 green.
    python3 scripts/probes/_717_shape_gates_1111/06_qm_blocked_sheet.py
-> qm_blocked_sheet.png + qm_blocked_sheet.key_do_not_show.txt"""
import csv
import gzip
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter, ScalarFormatter

sys.path.insert(0, ".")
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402

HERE = "scripts/probes/_717_shape_gates_1111/"
FX = Path("tests/fixtures/qm_breakout_scorecard")
by = defaultdict(list)
with gzip.open(FX / "bars.psv.gz", "rt") as fh:
    for r in csv.DictReader(fh, delimiter="|"):
        by[r["eid"]].append(r)
pool = []
for r in csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"):
    rr = sorted(by[r["eid"]], key=lambda x: x["date"])
    D = [x["date"] for x in rr].index(r["D"])
    rr = rr[:D + 1]                                           # the buy day never enters
    b = cb.daily_bars_from_arrays([date.fromisoformat(x["date"]) for x in rr], *[[float(x[k]) for x in rr] for k in "ohlcv"])
    v = bv.v1_gates(b, D, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))
    if not v["ok"]:
        continue
    sg = bv.shape_gates(b, D, P=v["pole_idx"], adr20=v["adr20"])
    pool.append((r, b, D, v, sg, [k for k in bv.SHAPE_GATES if not sg[k]["pass"]]))
rng = random.Random(1111)
picked, seen = [], set()
for gate in ("higher_lows", "no_lower_low", "rising_avg"):
    cands = [x for x in pool if gate in x[5] and x[0]["eid"] not in seen]
    for x in rng.sample(cands, 4):
        picked.append((gate, x))
        seen.add(x[0]["eid"])
rng.shuffle(picked)


def ema(x, n):
    k, o = 2 / (n + 1), np.empty(len(x))
    o[0] = x[0]
    for i in range(1, len(x)):
        o[i] = k * x[i] + (1 - k) * o[i - 1]
    return o


fig = plt.figure(figsize=(26, 18))
gs = fig.add_gridspec(6, 4, height_ratios=[3, 1] * 3, hspace=0.45, wspace=0.12)
key = []
for n, (gate, (r, b, D, v, sg, failed)) in enumerate(picked):
    L = chr(ord("A") + n)
    off = max(0, len(b) - 130)
    o, h, l, c, vol = (np.asarray(x, float)[off:] for x in (b.o, b.h, b.l, b.c, b.v))
    cf = np.asarray(b.c, float)
    rr, cc = divmod(n, 4)
    ax = fig.add_subplot(gs[2 * rr, cc])
    axv = fig.add_subplot(gs[2 * rr + 1, cc], sharex=ax)
    for k in range(len(c)):
        col = "#26a69a" if c[k] >= o[k] else "#ef5350"
        ax.vlines(k, l[k], h[k], color=col, lw=0.9)
        ax.add_patch(plt.Rectangle((k - 0.3, min(o[k], c[k])), 0.6, max(abs(c[k] - o[k]), 1e-9), color=col))
        axv.bar(k, vol[k], color=col, width=0.7)
    s50 = np.full(len(cf), np.nan)
    cs = np.cumsum(np.insert(cf, 0, 0.0))
    s50[49:] = (cs[50:] - cs[:-50]) / 50
    for arr, col in ((ema(cf, 10), "#1f77b4"), (ema(cf, 21), "#d62728"), (s50, "#2ca02c")):
        ax.plot(range(len(c)), arr[off:], color=col, lw=0.9)
    P = v["pole_idx"]
    B = P + 1 + int(np.argmin(np.asarray(b.l, float)[P + 1:D + 1]))
    ax.axvline(P - off, color="grey", ls=":", lw=1.2)
    ax.axvline(B - off, color="#ff7f0e", ls=":", lw=1.2)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(ScalarFormatter())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.hlines(v["level"], len(c) - 30, len(c) - 1, colors="black", linestyles="dashed", lw=1.0)
    ax.set_title(L, fontsize=13, loc="left")
    ax.tick_params(labelsize=6)
    axv.tick_params(labelsize=5)
    ax.set_xticks([])
    axv.set_xticks([])
    key.append(f"{L}|{r['sym']}|{r['E']}|{r['big_winner']}|{r['his_label'] or '-'}|drawn for {gate}|fails {','.join(failed)}|base {D - P} sessions, bottom {D - B} sessions before D")
fig.suptitle("12 Qullamaggie breakout buys the first shape gates BLOCK — each chart ends the night before his buy (~6 months of daily bars). "
             "Dashed = the 5-day high; grey dotted = the pole top the list found; orange dotted = the base's lowest low.", fontsize=12)
fig.savefig(HERE + "qm_blocked_sheet.png", dpi=100, bbox_inches="tight")
open(HERE + "qm_blocked_sheet.key_do_not_show.txt", "w").write(
    "letter|sym|his buy day E|big winner|his label|drawn for|fails|base\n" + "\n".join(key) + "\n")
print("ok", len(picked))
