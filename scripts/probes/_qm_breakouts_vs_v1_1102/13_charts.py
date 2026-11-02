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
from _chartlib import D, ema, panel, sheet  # noqa

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
