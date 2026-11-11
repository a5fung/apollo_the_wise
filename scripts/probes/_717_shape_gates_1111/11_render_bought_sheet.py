#!/usr/bin/env python3
"""#717 DoD (3): the outcome-blind sheet of the names the list would BUY FIRST — the top N by the order score, re-ranked
over the names that survive the shape gates (not random list names). Each chart ends on the list night; the dashed line
is the name's level (the 5-day high). NOT shown: ticker, rank, score. Same drawing as
scripts/probes/_717_grading_sheet_1107/render.py (daily candles, EMA10 / EMA21 / SMA50 / SMA200, volume, log scale).

    python3 scripts/probes/_717_shape_gates_1111/11_render_bought_sheet.py \
        [--inp scripts/probes/_717_shape_gates_1111/10_sheet_latest_list.out] [--gates not_extended,tight10 | none] \
        [--n 12] [--seed 1111] [--out scripts/probes/_717_shape_gates_1111/bought_sheet.png]

Input = the psql output of 10_sheet_latest_list.sql (a `== LIST` block, then a `== BARS` block). Writes the PNG and
`<out>.key_do_not_show.txt` (letter | ticker | new rank | old rank | level | failed gates of the names left out).
No bar after the list night exists in the input, so no outcome can be seen."""
import argparse
import random
import sys
from collections import defaultdict
from datetime import date

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter, ScalarFormatter

sys.path.insert(0, ".")
from agents.market_intelligence import breakout_v1 as bv, breakout_v1_list as bl, consolidation_breakout as cb  # noqa: E402

HERE = "scripts/probes/_717_shape_gates_1111/"
ap = argparse.ArgumentParser()
ap.add_argument("--inp", default=HERE + "10_sheet_latest_list.out")
ap.add_argument("--gates", default="not_extended,tight10")
ap.add_argument("--n", type=int, default=12)
ap.add_argument("--seed", type=int, default=1111)
ap.add_argument("--out", default=HERE + "bought_sheet.png")
a = ap.parse_args()
GATES = [] if a.gates == "none" else a.gates.split(",")
assert all(g in bv.SHAPE_GATES for g in GATES), GATES

lst, bars, sec = [], defaultdict(list), None
for line in open(a.inp):
    line = line.strip()
    if line.startswith("== "):
        sec = line[3:]
    elif sec == "LIST" and line[:2] == "20":
        d, t, rk, lvl, sc, adr, ru, sp = line.split("|")
        lst.append({"scan_date": d, "ticker": t, "old_rank": int(rk), "level": float(lvl),
                    "runup6m_adr": float(ru) if ru else None, "spread10_adr": float(sp) if sp else None})
    elif sec == "BARS" and line.count("|") == 6 and line.split("|")[1][:2] == "20":
        t, d, o, h, l, c, v = line.split("|")
        bars[t].append((date.fromisoformat(d), float(o), float(h), float(l), float(c), float(v)))
assert lst, "no == LIST rows"
night = lst[0]["scan_date"]

kept, left_out = [], []
for r in lst:
    rows = bars[r["ticker"]]
    assert rows and rows[-1][0].isoformat() == night, (r["ticker"], "bars must end on the list night")
    b = cb.daily_bars_from_arrays([x[0] for x in rows], *[[x[i] for x in rows] for i in range(1, 6)])
    D = len(b) - 1
    v = bv.v1_gates(b, D, rs_best=99.0)                       # it is on the list; only the pole and ADR are needed
    sg = bv.shape_gates(b, D, P=v["pole_idx"], adr20=v["adr20"])
    failed = [g for g in GATES if not sg[g]["pass"]]
    r["bars"] = b
    (left_out if failed else kept).append(dict(r, failed=failed))
bl.rank_rows(kept)                                            # the order score re-ranked over the survivors
top = kept[:a.n]
random.Random(a.seed).shuffle(top)                            # the letter says nothing about the rank


def ema(x, n):
    k, o = 2 / (n + 1), np.empty(len(x))
    o[0] = x[0]
    for i in range(1, len(x)):
        o[i] = k * x[i] + (1 - k) * o[i - 1]
    return o


def sma(x, n):
    out = np.full(len(x), np.nan)
    cs = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


ncol = 4
nrow = (len(top) + ncol - 1) // ncol
fig = plt.figure(figsize=(26, 6 * nrow))
gs = fig.add_gridspec(2 * nrow, ncol, height_ratios=[3, 1] * nrow, hspace=0.45, wspace=0.12)
key = []
for n, r in enumerate(top):
    L = chr(ord("A") + n)
    b = r["bars"]
    c_full = np.asarray(b.c, float)
    off = max(0, len(b) - 252)
    o, h, l, c, v = (np.asarray(x, float)[off:] for x in (b.o, b.h, b.l, b.c, b.v))
    rr, cc = divmod(n, ncol)
    ax = fig.add_subplot(gs[2 * rr, cc])
    axv = fig.add_subplot(gs[2 * rr + 1, cc], sharex=ax)
    for k in range(len(c)):
        col = "#26a69a" if c[k] >= o[k] else "#ef5350"
        ax.vlines(k, l[k], h[k], color=col, lw=0.7)
        ax.add_patch(plt.Rectangle((k - 0.3, min(o[k], c[k])), 0.6, max(abs(c[k] - o[k]), 1e-9), color=col))
        axv.bar(k, v[k], color=col, width=0.7)
    for arr, col in ((ema(c_full, 10), "#1f77b4"), (ema(c_full, 21), "#d62728"), (sma(c_full, 50), "#2ca02c"), (sma(c_full, 200), "#9467bd")):
        ax.plot(range(len(c)), arr[off:], color=col, lw=0.9)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(ScalarFormatter())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.hlines(r["level"], len(c) - 30, len(c) - 1, colors="black", linestyles="dashed", lw=1.0)
    ax.set_title(L, fontsize=13, loc="left")
    ax.tick_params(labelsize=6)
    axv.tick_params(labelsize=5)
    ax.set_xticks([])
    axv.set_xticks([])
    key.append(f"{L}|{r['ticker']}|{r['list_rank']}|{r['old_rank']}|{r['level']}")
fig.suptitle(f"Breakout list, {night} — the {len(top)} names it would buy first; ~1 year of daily bars ending on the list night; "
             "the dashed line is the breakout level (the 5-day high). For each: a real breakout setup? good / ok / no", fontsize=12)
fig.savefig(a.out, dpi=100, bbox_inches="tight")
with open(a.out + ".key_do_not_show.txt", "w") as f:
    f.write(f"#717 bought-names sheet, list night {night}: gates {GATES or 'none (the current list)'}; {len(lst)} on the list, "
            f"{len(kept)} survive, top {len(top)} by the re-ranked order score, shuffled (seed {a.seed}). NOT shown: ticker, rank, score.\n")
    f.write("letter|ticker|new_rank|old_rank|level\n" + "\n".join(key) + "\n")
    f.write("\nleft out by the gates (ticker|old_rank|failed):\n" + "\n".join(f"{r['ticker']}|{r['old_rank']}|{','.join(r['failed'])}" for r in left_out) + "\n")
print(f"{a.out}: night {night}, {len(lst)} listed, {len(kept)} survive {GATES}, sheet of {len(top)}")
