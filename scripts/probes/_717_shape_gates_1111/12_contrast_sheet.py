#!/usr/bin/env python3
"""#717: his good/ok charts that the higher-lows / rising-average gates reject (top) vs his `no` charts that pass
every gate (bottom). Question for him: what separates the top row from the bottom? Bars end on the list night."""
import gzip, sys
from collections import defaultdict
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter, ScalarFormatter
sys.path.insert(0, ".")
from tests.fixtures.breakout_list_grades import BREAKOUT_LIST_GRADES as G
TOP = ["RSKD", "FNKO", "MANE", "CVLT", "IAG"]; BOT = ["ABCL", "NVAX", "SIG"]
grade = {g.ticker: g for g in G}
bars = defaultdict(list)
with gzip.open("tests/fixtures/breakout_list_grades_bars.psv.gz", "rt") as f:
    next(f)
    for line in f:
        t, ld, d, o, h, l, c, v = line.strip().split("|")
        if t in grade and ld == grade[t].list_date:
            bars[t].append((d, *map(float, (o, h, l, c, v))))
def ema(x, n):
    k, o = 2 / (n + 1), np.empty(len(x)); o[0] = x[0]
    for i in range(1, len(x)): o[i] = k * x[i] + (1 - k) * o[i - 1]
    return o
def sma(x, n):
    out = np.full(len(x), np.nan); cs = np.cumsum(np.insert(x, 0, 0.0)); out[n - 1:] = (cs[n:] - cs[:-n]) / n; return out
fig = plt.figure(figsize=(30, 12)); gs = fig.add_gridspec(4, 5, height_ratios=[3, 1, 3, 1], hspace=0.4, wspace=0.12)
for row, names in ((0, TOP), (1, BOT)):
    for col, t in enumerate(names):
        rows = sorted(bars[t]); a = np.array([r[1:] for r in rows]); cf = a[:, 3]; off = max(0, len(a) - 180)
        o, h, l, c, v = (a[off:, i] for i in range(5))
        ax = fig.add_subplot(gs[2 * row, col]); axv = fig.add_subplot(gs[2 * row + 1, col], sharex=ax)
        for k in range(len(c)):
            cl = "#26a69a" if c[k] >= o[k] else "#ef5350"
            ax.vlines(k, l[k], h[k], color=cl, lw=0.7)
            ax.add_patch(plt.Rectangle((k - 0.3, min(o[k], c[k])), 0.6, max(abs(c[k] - o[k]), 1e-9), color=cl)); axv.bar(k, v[k], color=cl, width=0.7)
        for arr, cl in ((ema(cf, 10), "#1f77b4"), (ema(cf, 21), "#d62728"), (sma(cf, 50), "#2ca02c")):
            ax.plot(range(len(c)), arr[off:], color=cl, lw=0.9)
        ax.set_yscale("log"); ax.yaxis.set_major_formatter(ScalarFormatter()); ax.yaxis.set_minor_formatter(NullFormatter())
        ax.hlines(grade[t].level, len(c) - 30, len(c) - 1, colors="black", linestyles="dashed", lw=1.0)
        g = grade[t]; ax.set_title(f"{t} {g.list_date} — you: {g.operator_words[:40]}", fontsize=11, loc="left")
        ax.tick_params(labelsize=6); axv.tick_params(labelsize=5); ax.set_xticks([]); axv.set_xticks([])
fig.suptitle("TOP: you said good/ok, but our higher-lows / rising-average rules reject them.   BOTTOM: you said no, but every rule passes them.   "
             "What separates top from bottom?  (~9 months daily; blue EMA10, red EMA21, green SMA50; dashed = breakout level)", fontsize=13)
out = "scripts/probes/_717_shape_gates_1111/contrast_sheet.png"; fig.savefig(out, dpi=90, bbox_inches="tight"); print(out)
