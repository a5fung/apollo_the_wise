#!/usr/bin/env python3
"""Charts for his review (11-02 method): (1) the 11 of Qullamaggie's breakout buys the rebuilt rules drop — the chart up to
and including his buy day (arrow), so the setup is shown, not the outcome; (2) ONE sample night of the rebuilt list: his buy +
11 other listed names drawn at random (seed 1102), shuffled and lettered A-L so the review is blind. Daily candles,
EMA10 / EMA21 / SMA50 / SMA200 (his chart's averages), volume. Split-adjusted prices. Local store, nothing 2025+."""
import os, sys, json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
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

# (1) the 11 dropped buys
dr = pd.read_csv(f"{HERE}/backward/12_dropped_buys.tsv", sep="\t")
def why(r):
    if r.feature == "adr20": return f"daily range {r.value:.2%} (rule: at least 2.80%)"
    if r.feature == "prior_move": return f"run-up {r.value:.1%} (rule: at least 32.1%)"
    return f"base depth {r.value:.1f} daily ranges (rule: 1.7 to 9.0)"
items = [(r.ticker, r.E, r.E, f"{r.sym}  ·  his buy {r.E} (arrow)\nleft off by: {why(r)}") for r in dr.itertuples()]
sheet(items, f"{HERE}/charts/dropped_11.png", "Qullamaggie's breakout buys the rebuilt rules drop (chart up to his buy day)")

# (2) one sample night, blind
rules = json.load(open(f"{HERE}/backward/12_final_rules.json"))
print("rules:", rules)

# (2) ONE sample night of the rebuilt list, blind: the night before one of his big winners whose list size is nearest the
# median night; his buy + 11 other names on the list that night (random, seed 1102); charts end at the night (no buy day).
def on_list(df):
    m = (df.pass_history == 1) & (df.pass_universe == 1) & (df.rs_best >= 35) & (df.adr20 >= 0.021) & (df.pass_prior_move == 1)
    for r in rules["added_rules"]:
        v = df.eval(r["expr"])
        m &= (v >= r["lo"]) & (v <= r["hi"]) if r["op"] == "band" else (v >= r["threshold"])
    return m
cols = ["scan_date", "ticker", "pass_history", "pass_universe", "rs_best", "adr20", "pass_prior_move", "prior_move",
        "prior_move.pole_high", "higher_lows.base_low"]
Fa = pd.read_parquet("/Users/alvinfung/apollo_data/qm_breakouts_1102/features_eraA.parquet", columns=cols)
Fa = Fa[on_list(Fa)]
sizes = Fa.groupby("scan_date").size()
Q = pd.read_csv(f"{HERE}/qm_breakouts_v1_gates.tsv.gz", sep="\t")
t = pd.read_csv("/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/replay/trades.tsv.gz", sep="\t", usecols=["eid", "arm", "in_window", "entry_status", "realized_r"])
w = t[(t.arm == "d3_p33_tspd") & (t.in_window == True) & (t.entry_status == "filled")]
big = Q[Q.eid.isin(set(w[w.realized_r >= 5].eid)) & Q.D.isin(sizes.index)].copy()
big["n"] = big.D.map(sizes); med = sizes.median()
# disclosed after a first render: the rule picked 2020-02-25, the first night of the 2020 crash (every chart ended in the
# same two-day drop) — the crash window 2020-02-20..2020-04-30 is excluded so the sheet shows an ordinary night
big = big[~big.D.between("2020-02-20", "2020-04-30")]
pick = big.iloc[(big.n - med).abs().argsort()].iloc[0]
night = Fa[Fa.scan_date == pick.D]
others = night[night.ticker != pick.ticker].sample(11, random_state=1102).ticker.tolist()
names = [pick.ticker] + others
rng = np.random.default_rng(1102); order = rng.permutation(len(names))
letters = "ABCDEFGHIJKL"
key = {letters[i]: names[k] for i, k in enumerate(order)}
json.dump({"night": pick.D, "his_buy": pick.ticker, "his_buy_day": pick.E, "list_size_that_night": int(pick.n),
           "median_list_size": float(med), "key": key}, open(f"{HERE}/charts/sample_night_KEY.json", "w"), indent=1)
items = [(key[L], pick.D, None, f"{L}") for L in letters]
sheet(items, f"{HERE}/charts/sample_night_blind.png",
      f"One night of the rebuilt list ({int(pick.n)} names that night): 12 of them, lettered, charts end that night — which are setups?")
print("sample night", pick.D, "list size", int(pick.n), "median", med)
