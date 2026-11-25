#!/usr/bin/env python3
"""VOR vs the 6 Qullamaggie big winners our base detector saw no base on (his 11-25 "show me these charts compared to vor").
$0, offline. Daily candles, 120 sessions ending on the buy day (orange marker), 50-day average in blue."""
import csv, gzip, sys
from collections import defaultdict
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import numpy as np
REPO = Path(__file__).resolve().parents[3]; HERE = Path(__file__).parent; FX = REPO / "tests/fixtures/qm_breakout_scorecard"
N = 120
want = [("APT", "2020-06-17"), ("MDB", "2020-09-21"), ("JMIA", "2020-11-18"), ("SKLZ", "2021-01-05"), ("OSTK", "2021-01-22"), ("QS", "2021-10-29")]
buys = {(r["sym"], r["E"]): r["eid"] for r in csv.DictReader(open(FX / "buys.tsv"), delimiter="\t")}
by = defaultdict(list)
with gzip.open(FX / "bars.psv.gz", "rt") as f:
    for r in csv.DictReader(f, delimiter="|"): by[r["eid"]].append(r)
panels = []
v = [l.strip().split("|") for l in open(HERE / "vor_bars.psv") if l[:2] == "20"]
panels.append(("VOR 2026-11-23 — our paper buy (stopped 11-25)", [(x[0], *map(float, x[1:5])) for x in v], "2026-11-23"))
for s, e in want:
    rr = sorted(by[buys[(s, e)]], key=lambda x: x["date"])
    panels.append((f"{s} {e} — Qullamaggie buy, big winner", [(x["date"], float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"])) for x in rr], e))
fig, axs = plt.subplots(4, 2, figsize=(14, 16)); axs = axs.ravel()
for ax, (title, rows, E) in zip(axs, panels):
    dates = [r[0] for r in rows]; k = dates.index(E); rows_all = rows; rows = rows[max(0, k - N + 1):k + 1]
    o, h, l, c = (np.array([r[i] for r in rows]) for i in (1, 2, 3, 4))
    call = np.array([r[4] for r in rows_all[:k + 1]]); sma = np.convolve(call, np.ones(50) / 50, "valid")[-len(rows):]
    x = np.arange(len(rows))
    for i in x:
        col = "#2e7d32" if c[i] >= o[i] else "#c62828"
        ax.vlines(i, l[i], h[i], color=col, lw=0.8); ax.add_patch(plt.Rectangle((i - 0.35, min(o[i], c[i])), 0.7, max(abs(c[i] - o[i]), 1e-6), color=col))
    ax.plot(x[-len(sma):], sma, color="#1565c0", lw=1)
    ax.axvline(x[-1], color="orange", lw=1.5, alpha=0.6)
    ax.set_title(title, fontsize=11, fontweight="bold" if title.startswith("VOR") else None)
    ax.set_xticks([0, len(x) // 2, len(x) - 1]); ax.set_xticklabels([rows[0][0], rows[len(x) // 2][0], rows[-1][0]], fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
axs[-1].axis("off")
fig.suptitle("Daily, 120 sessions to the buy day (orange). Our base detector found NO base the night before on all seven.", fontsize=12)
fig.tight_layout(rect=(0, 0, 1, 0.97)); out = HERE / "vor_vs_qm_no_base.png"; fig.savefig(out, dpi=110); print(out)
