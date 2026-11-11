"""The sheet drawing (as scripts/probes/_717_shape_gates_1111/11_render_bought_sheet.py): ~1 year of daily candles ending
on `hi`, EMA10 blue / EMA21 red / SMA50 green / SMA200 purple, volume, log scale; the buy point dashed; the buy window shaded."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter, ScalarFormatter


def ema(x, n):
    k, o = 2 / (n + 1), np.empty(len(x))
    o[0] = x[0]
    for i in range(1, len(x)):
        o[i] = k * x[i] + (1 - k) * o[i - 1]
    return o


def sma(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def render(items, out, title, key_head, key_line, bars_shown=252):
    """items = [(b, r)] in sheet order; key_line(b, r) -> the text after the letter."""
    ncol = 4
    nrow = (len(items) + ncol - 1) // ncol
    fig = plt.figure(figsize=(26, 6 * nrow))
    gs = fig.add_gridspec(2 * nrow, ncol, height_ratios=[3, 1] * nrow, hspace=0.45, wspace=0.12)
    key = []
    for n, (b, r) in enumerate(items):
        L = chr(ord("A") + n)
        cf = b["c"]
        off = max(0, len(cf) - bars_shown)
        o, h, l, c, v = (b[k][off:] for k in "ohlcv")
        rr, cc = divmod(n, ncol)
        ax = fig.add_subplot(gs[2 * rr, cc])
        axv = fig.add_subplot(gs[2 * rr + 1, cc], sharex=ax)
        for k in range(len(c)):
            col = "#26a69a" if c[k] >= o[k] else "#ef5350"
            ax.vlines(k, l[k], h[k], color=col, lw=0.7)
            ax.add_patch(plt.Rectangle((k - 0.3, min(o[k], c[k])), 0.6, max(abs(c[k] - o[k]), 1e-9), color=col))
            axv.bar(k, v[k], color=col, width=0.7)
        for arr, col in ((ema(cf, 10), "#1f77b4"), (ema(cf, 21), "#d62728"), (sma(cf, 50), "#2ca02c"), (sma(cf, 200), "#9467bd")):
            ax.plot(range(len(c)), arr[off:], color=col, lw=0.9)
        ax.axvspan(b["win"][0] - off - 0.5, b["win"][-1] - off + 0.5, color="#ffd54f", alpha=0.35, lw=0)
        if r.get("level") is not None:
            ax.hlines(r["level"], max(0, r["p"] - off), len(c) - 1, colors="black", linestyles="dashed", lw=1.0)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(ScalarFormatter())
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_title(L, fontsize=13, loc="left")
        ax.tick_params(labelsize=6)
        axv.tick_params(labelsize=5)
        ax.set_xticks([])
        axv.set_xticks([])
        key.append(f"{L}|{key_line(b, r)}")
    fig.suptitle(title, fontsize=12)
    fig.savefig(out, dpi=100, bbox_inches="tight")
    plt.close(fig)
    open(out + ".key_do_not_show.txt", "w").write(key_head + "\n" + "\n".join(key) + "\n")
