#!/usr/bin/env python3
"""#594 sample #5 page: the 8 drawn gap days (key_do_not_show.txt), each chart ending the session BEFORE the gap day, lettered
A-H, no ticker, date, score or outcome shown (outcome-blind, his 10-10 ruling). Daily candles, EMA10/EMA21/SMA50/SMA200, volume."""
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter, NullFormatter
key = [l.split("|") for l in open("key_do_not_show.txt").read().strip().split("\n")[2:]]  # key rows
blocks, cur = {}, None
for l in open("q2_bars.out"):
    l = l.strip()
    if l.startswith("== "): cur = tuple(l[3:].split()); blocks[cur] = []
    elif cur and l[:2] == "20": blocks[cur].append([float(x) if i else x for i, x in enumerate(l.split("|"))])
def ema(x, n):
    a, o = 2 / (n + 1), np.empty(len(x)); o[0] = x[0]
    for i in range(1, len(x)): o[i] = a * x[i] + (1 - a) * o[i - 1]
    return o
fig = plt.figure(figsize=(26, 18)); gs = fig.add_gridspec(6, 4, height_ratios=[3, 1, 3, 1, 3, 1], hspace=0.45, wspace=0.12)
for n, (L, t, d, *_rest) in enumerate(key):
    b = pd.DataFrame(blocks[(t, d)], columns=["date", "o", "h", "l", "c", "v"]).tail(504).reset_index(drop=True)
    full = pd.DataFrame(blocks[(t, d)], columns=["date", "o", "h", "l", "c", "v"])
    off = len(full) - len(b)
    r, cc = divmod(n, 4); ax = fig.add_subplot(gs[2 * r, cc]); axv = fig.add_subplot(gs[2 * r + 1, cc], sharex=ax)
    for k, row in b.iterrows():
        col = "#26a69a" if row.c >= row.o else "#ef5350"
        ax.vlines(k, row.l, row.h, color=col, lw=0.7); ax.add_patch(plt.Rectangle((k - 0.3, min(row.o, row.c)), 0.6, max(abs(row.c - row.o), 1e-9), color=col))
        axv.bar(k, row.v, color=col, width=0.7)
    c = full.c.values
    for arr, col in ((ema(c, 10), "#1f77b4"), (ema(c, 21), "#d62728"), (pd.Series(c).rolling(50).mean().values, "#2ca02c"), (pd.Series(c).rolling(200).mean().values, "#9467bd")):
        ax.plot(range(len(b)), arr[off:], color=col, lw=0.9)
    ax.set_yscale("log"); ax.yaxis.set_major_formatter(ScalarFormatter()); ax.yaxis.set_minor_formatter(NullFormatter())
    ax.axvline(len(b) - 1, color="orange", lw=1.0, alpha=0.6)
    ax.set_title(f"{L}", fontsize=13, loc="left"); ax.tick_params(labelsize=6); axv.tick_params(labelsize=5)
    ax.set_xticks([]); axv.set_xticks([])
fig.suptitle("#594 sample 7 — 12 real gap days, ~2 years of history; the LAST bar (orange line) is the gap day itself; nothing after it (no ticker, date, score or result). For each: good / ok / bad?", fontsize=12)
fig.savefig("sample7_blind.png", dpi=100, bbox_inches="tight")
print("ok")
