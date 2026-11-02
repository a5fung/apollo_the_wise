#!/usr/bin/env python3
"""Stage 0 shared frames. The rebuilt list (rules 1-7 of docs/analysis/cb_rebuild_from_qm_trades_2026-11-02.md) is
RE-IMPLEMENTED here from the feature-table columns (14 -> 15 -> 17 -> 18's NEW mask), never by running those scripts
(they rewrite their own outputs in the parent folder). Thresholds are read from the same files they read
(backward/12_final_rules.json, 15_ema21_drops.tsv). Parity with 18_sma50_rule.txt is asserted by s0.py.
Qullamaggie's buys = qm_breakouts_v1_gates.tsv.gz (269); big winners = 11_starting_point.py's definition.
No returns are used for any rule or count: the big-winner flag is the scorecard's label only."""
import json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
REPO = "/Users/alvinfung/apollo_the_wise"
OUTDIR = "/Users/alvinfung/apollo_data/qm_breakouts_1102"
os.environ.setdefault("BV1_SCRATCH", "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/"
                                     "d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/qmbo1102")
for p in (REPO, "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101"):
    if p not in sys.path:
        sys.path.insert(0, p)

ERA_B_D_FIRST = "2022-04-01"
COLS = ["scan_date", "E", "ticker", "pass_history", "pass_universe", "rs_best", "adr20", "pass_prior_move", "prior_move",
        "prior_move.pole_high", "higher_lows.base_low", "close", "e21", "breakdown.sma50", "level"]


def load():
    F = pd.concat([pd.read_parquet(f"{OUTDIR}/features_era{e}.parquet", columns=COLS) for e in "AB"], ignore_index=True)
    depth = (F["prior_move.pole_high"] - F["higher_lows.base_low"]) / F["prior_move.pole_high"] / F["adr20"]
    vs21 = (F.close / F.e21 - 1) / F.adr20
    vs50 = F.close / F["breakdown.sma50"] - 1
    R = {r["feature"]: r for r in json.load(open(f"{PARENT}/backward/12_final_rules.json"))["added_rules"]}
    Q = pd.read_csv(f"{PARENT}/qm_breakouts_v1_gates.tsv.gz", sep="\t")
    t = pd.read_csv("/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/replay/trades.tsv.gz", sep="\t",
                    usecols=["eid", "arm", "in_window", "entry_status", "realized_r"])
    w = t[(t.arm == "d3_p33_tspd") & (t.in_window == True) & (t.entry_status == "filled")]
    Q["big"] = Q.eid.isin(set(w[w.realized_r >= 5].eid))          # the scorecard's big-winner label (11_starting_point)
    del t, w
    idx = pd.Series(F.index, index=pd.MultiIndex.from_arrays([F.ticker, F.scan_date]))
    Q["row"] = [idx.get((a, b)) for a, b in zip(Q.ticker, Q.D)]
    assert Q.row.notna().all()
    Q["row"] = Q.row.astype(int)
    # 14: the start + his labels' loosening
    S0 = (F.pass_history == 1) & (F.pass_universe == 1) & (F.rs_best >= 35) & (F.adr20 >= 0.021) & (F.pass_prior_move == 1)
    LRN = float(depth.loc[Q.row[(Q.sym == "LRN") & (Q.E == "2020-08-05")]].iloc[0])
    AFTER = S0 & depth.between(LRN, R["base_depth_adr"]["hi"]) & (F.prior_move >= R["prior_move"]["threshold"])
    # 17: close vs EMA21 loosened to TSLA's value (15_ema21_drops.tsv, read only)
    d = pd.read_csv(f"{PARENT}/15_ema21_drops.tsv", sep="\t")
    th21 = float(d.loc[d.sym == "TSLA", "vs21"].iloc[0])
    CUR = AFTER & (vs21 >= th21)
    # 18: the plain line close >= 50-day SMA
    NEW = CUR & (vs50 >= 0.0)
    eraB = F.scan_date >= ERA_B_D_FIRST
    return dict(F=F, Q=Q, NEW=NEW, eraB=eraB, th=dict(LRN=LRN, depth_hi=R["base_depth_adr"]["hi"],
                                                      prior_move=R["prior_move"]["threshold"], vs21=th21))


def labels(F, Q):
    """His 95 labels exactly as 32_tight_recently.py builds them (the newer label wins)."""
    key = {(t, d): i for i, t, d in zip(F.index, F.ticker, F.scan_date)}
    symtk = dict(zip(Q.sym, Q.ticker))
    L1 = pd.read_csv(f"{PARENT}/27_loose_wide_labels.tsv", sep="\t")[["who", "sym", "D", "label", "yes"]]
    L2 = pd.read_csv(f"{PARENT}/31_tight3_labels.tsv", sep="\t")
    L2 = pd.DataFrame({"who": "QM buy", "sym": L2.sym, "D": L2.D, "label": L2.his,
                       "yes": L2.his.str.startswith(("ok", "good")) | L2.his.str.contains("earlier") & ~L2.his.str.startswith("no")})
    L2.loc[L2.label.str.startswith("no") | L2.label.str.contains("EP"), "yes"] = False
    L = pd.concat([L1[~L1.set_index(["sym", "D"]).index.isin(L2.set_index(["sym", "D"]).index)], L2])
    L["i"] = [key.get((symtk.get(s, s) if w == "QM buy" else s, d)) for s, d, w in zip(L.sym, L.D, L.who)]
    L = L[L.i.notna()].copy(); L["i"] = L.i.astype(int)
    return L


def bar_features(D, runner, F, rows_mask):
    """Per (ticker, night) row in `rows_mask`: from the store D's daily bars <= D (and the E bar for the trigger):
    move126 (23), c10 (32), the daily buy test pieces (36): up = high(E) > 5-day high to D, x10 / x50 = volume(E) /
    the 10 / 50-session average to D, E_bar = the next stored session."""
    parts = []
    sub = F[rows_mask]
    for tk, grp in sub.groupby("ticker"):
        b, _ = runner.bars_for(D, D.tid[tk])
        h, l, c, v = (pd.Series(np.asarray(x, float)) for x in (b.h, b.l, b.c, b.v))
        m126 = (h / l.rolling(64, min_periods=1).min() - 1).rolling(126, min_periods=1).max()
        adr = ((h - l) / c).rolling(20).mean()
        c10 = (c.rolling(10).max() / c.rolling(10).min() - 1) / adr
        lvl = h.rolling(5).max(); up = h.shift(-1) > lvl
        x10 = v.shift(-1) / v.rolling(10).mean(); x50 = v.shift(-1) / v.rolling(50).mean()
        pos = {d.isoformat(): i for i, d in enumerate(b.dates)}; ii = [pos[d] for d in grp.scan_date]
        nxt = [b.dates[i + 1].isoformat() if i + 1 < len(b.dates) else None for i in ii]
        parts.append(pd.DataFrame({"idx": grp.index, "move126": m126.values[ii], "c10": c10.values[ii], "up": up.values[ii],
                                   "x10": x10.values[ii], "x50": x50.values[ii], "lvl5": lvl.values[ii], "E_bar": nxt}))
    return pd.concat(parts).set_index("idx").sort_index()
