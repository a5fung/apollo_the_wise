"""Chart helpers shared by 13_charts.py and 16_charts_ema21.py (daily candles, EMA10/EMA21/SMA50/SMA200, volume)."""
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from scripts.probes._cb_backtest import runner  # noqa
D = runner.load_daily("/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz")

def ema(x, n):
    a, o = 2 / (n + 1), np.empty(len(x)); o[0] = x[0]
    for i in range(1, len(x)): o[i] = a * x[i] + (1 - a) * o[i - 1]
    return o

def panel(ax, axv, tk, last, mark=None, title="", n=130):
    b, _ = runner.bars_for(D, D.tid[tk]); dates = list(b.dates)
    j = dates.index(pd.Timestamp(last).date()); lo = max(0, j - n + 1)
    c = np.asarray(b.c, float); o = np.asarray(b.o, float); h = np.asarray(b.h, float); l = np.asarray(b.l, float); v = np.asarray(b.v, float)
    lines = {"EMA10": (ema(c, 10), "#1f77b4"), "EMA21": (ema(c, 21), "#d62728"),
             "SMA50": (pd.Series(c).rolling(50).mean().values, "#2ca02c"), "SMA200": (pd.Series(c).rolling(200).mean().values, "#9467bd")}
    x = np.arange(j - lo + 1)
    for k, i in enumerate(range(lo, j + 1)):
        up = c[i] >= o[i]; col = "#26a69a" if up else "#ef5350"
        ax.vlines(k, l[i], h[i], color=col, lw=0.7); ax.add_patch(plt.Rectangle((k - 0.3, min(o[i], c[i])), 0.6, max(abs(c[i] - o[i]), 1e-9), color=col))
        axv.bar(k, v[i], color=col, width=0.7)
    for name, (arr, col) in lines.items():
        ax.plot(x, arr[lo:j + 1], color=col, lw=0.9, label=name)
    if mark is not None:
        m = dates.index(pd.Timestamp(mark).date()) - lo
        ax.annotate("", xy=(m, l[lo + m] * 0.97), xytext=(m, l[lo + m] * 0.85), arrowprops=dict(arrowstyle="->", color="orange", lw=2))
    ax.set_yscale("log"); ax.set_title(title, fontsize=10, loc="left")
    from matplotlib.ticker import ScalarFormatter, NullFormatter
    ax.yaxis.set_major_formatter(ScalarFormatter()); ax.yaxis.set_minor_formatter(NullFormatter()); ax.tick_params(labelsize=6); axv.tick_params(labelsize=5)
    ticks = list(range(0, len(x), 21)); ax.set_xticks(ticks); ax.set_xticklabels([]); axv.set_xticks(ticks)
    axv.set_xticklabels([dates[lo + t].strftime("%m-%d") for t in ticks], fontsize=6)

def sheet(items, path, suptitle, cols=3):
    rows = (len(items) + cols - 1) // cols
    fig = plt.figure(figsize=(6 * cols, 4.6 * rows))
    gs = fig.add_gridspec(2 * rows, cols, height_ratios=[3, 1] * rows, hspace=0.55, wspace=0.15)
    for n_, it in enumerate(items):
        r, cc = divmod(n_, cols)
        ax = fig.add_subplot(gs[2 * r, cc]); axv = fig.add_subplot(gs[2 * r + 1, cc], sharex=ax)
        panel(ax, axv, *it)
    fig.suptitle(suptitle, fontsize=12); fig.savefig(path, dpi=110, bbox_inches="tight"); plt.close(fig)

