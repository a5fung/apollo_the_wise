#!/usr/bin/env python3
"""Self-containment check of tests/fixtures/qm_breakout_scorecard: from its bars alone (+ rs_best / raw close at D), the live
v1_gates at D and the 7 rebuilt rules reproduce the research result per buy. This is the shape of the Saturday test."""
import gzip, json, sys
from datetime import date
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb
FX = "/Users/alvinfung/apollo_the_wise/tests/fixtures/qm_breakout_scorecard"
B = pd.read_csv(f"{FX}/buys.tsv", sep="\t")
X = pd.read_csv(f"{FX}/bars.psv.gz", sep="|")
R = json.load(open("/Users/alvinfung/apollo_the_wise/scripts/probes/_qm_breakouts_vs_v1_1102/backward/12_final_rules.json"))
rr = {r["feature"]: r for r in R["added_rules"]}
DLO, DHI, PM, E21 = 1.5113768339080410, rr["base_depth_adr"]["hi"], rr["prior_move"]["threshold"], -0.6335
def ema(x, n):
    a, o = 2 / (n + 1), np.empty(len(x)); o[0] = x[0]
    for i in range(1, len(x)): o[i] = a * x[i] + (1 - a) * o[i - 1]
    return o
ok, mism = 0, []
for r in B.itertuples():
    s = X[X.eid == r.eid].sort_values("date")
    dates = [date.fromisoformat(d) for d in s.date]
    bars = cb.daily_bars_from_arrays(dates, s.o.values, s.h.values, s.l.values, s.c.values, s.v.values)
    D = dates.index(date.fromisoformat(r.D))
    g = bv.v1_gates(bars, D, rs_best=r.rs_best, raw_close=r.raw_close_D)
    G = g["gates"]; c = s.c.values
    depth = (G["prior_move"]["value"]["pole_high"] - G["higher_lows"]["value"]["base_low"]) / G["prior_move"]["value"]["pole_high"] / g["adr20"]
    keep = (G["history"]["pass"] and G["universe"]["pass"] and r.rs_best >= 35 and g["adr20"] >= 0.021 and G["prior_move"]["pass"]
            and DLO <= depth <= DHI and g["prior_move"] >= PM and (c[D] / ema(c, 21)[D] - 1) / g["adr20"] >= E21
            and c[D] >= c[D - 49:D + 1].mean())
    ok += keep
    if int(keep) != r.on_rebuilt_list: mism.append((r.sym, r.D, int(keep), r.on_rebuilt_list))
print(f"from the fixture alone: {ok}/{len(B)} on the rebuilt list; mismatches vs the research result: {len(mism)} {mism[:8]}")
