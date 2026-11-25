#!/usr/bin/env python3
"""VOR 11-25 (his "go"): would requiring a FOUND BASE (breakout_v1.range_levels non-empty at night D) keep Qullamaggie's buys?
$0, offline, read-only; fixtures only (2017-2023). Research, no rule changed.
  python3 scripts/probes/_vor_1125/01_range_on_qm_buys.py > scripts/probes/_vor_1125/01_range_on_qm_buys.out
"""
import csv, gzip, sys
from collections import defaultdict
from datetime import date
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]; sys.path.insert(0, str(REPO))
from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import consolidation_breakout as cb
import numpy as np
FX = REPO / "tests/fixtures/qm_breakout_scorecard"

def load(bars_name):
    by = defaultdict(list)
    with gzip.open(FX / bars_name, "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            by[r["eid"]].append(r)
    out = {}
    for eid, rr in by.items():
        rr.sort(key=lambda x: x["date"]); ds = [date.fromisoformat(x["date"]) for x in rr]
        out[eid] = (ds, cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rr] for k in "ohlcv"]))
    return out

def has_range(b, D):
    return bool(bv.range_levels(np.asarray(b.h, float), np.asarray(b.l, float), D))

# 1) the 269 dated buys: D = the night before his buy day
B = load("bars.psv.gz"); rows = list(csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"))
hi = {r["eid"] for r in csv.DictReader(open(FX / "high_tier.tsv"), delimiter="\t") if r["set"] == "dated"}
n = found = big = big_found = h_n = h_found = listed = listed_found = 0; lost_big = []
for r in rows:
    ds, b = B[r["eid"]]; D = ds.index(date.fromisoformat(r["D"]))
    g = bv.v1_gates(b, D, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))
    f = has_range(b, D); n += 1; found += f
    if g["ok"]: listed += 1; listed_found += f
    if r["big_winner"] == "1":
        big += 1; big_found += f
        if not f: lost_big.append(f'{r["sym"]} {r["E"]}')
    if r["eid"] in hi: h_n += 1; h_found += f
print(f"DATED buys: base found the night before on {found} of {n} ({found/n:.0%}); on today's list {listed}, of them base found {listed_found}")
print(f"  big winners: base found {big_found} of {big}; lost: {', '.join(lost_big) or 'none'}")
print(f"  High-confidence tier: base found {h_found} of {h_n} (the High tier is defined by a range break, so this should be all)")

# 2) the 488 undated positions: base found on ANY night lo-1 .. hi-1
W = load("bars_undated_widened.psv.gz"); wr = list(csv.DictReader(open(FX / "buys_undated_widened.tsv"), delimiter="\t"))
m = mf = 0
for r in wr:
    if r["eid"] not in W: continue
    ds, b = W[r["eid"]]; lo, hi_ = date.fromisoformat(r["lo"]), date.fromisoformat(r["hi"])
    idx = [i - 1 for i, d in enumerate(ds) if lo <= d <= hi_ and i >= 1]
    if not idx: continue
    m += 1; mf += any(has_range(b, D) for D in idx)
print(f"UNDATED positions (setup unknown; some are funds or other setups): base found on some night of the buy window {mf} of {m} ({mf/m:.0%})")
