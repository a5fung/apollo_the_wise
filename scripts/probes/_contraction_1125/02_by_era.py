#!/usr/bin/env python3
"""His 11-25 guess: in 2020-21 (COVID crash + recovery) Qullamaggie may have bought looser charts. $0, offline.
Pass rate of the swings_shrink reading (C3, frozen in cb_contraction_into_buy_prereg_2026-11-25.md) on his 269 dated buys,
by buy year. A pass = tight (ratio <= T; unscored = pass, as frozen)."""
import csv, gzip, sys
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[3]; sys.path.insert(0, str(REPO))
from agents.market_intelligence import breakout_v1 as bv
FX = REPO / "tests/fixtures/qm_breakout_scorecard"
def r_c3(h, l, D, N):
    if D - N + 1 < 0: return None
    H, L = np.log(h[D-N+1:D+1]), np.log(l[D-N+1:D+1])
    if not (np.isfinite(H).all() and np.isfinite(L).all()): return None
    legs, _ = bv.swing_legs(H, L)
    if len(legs) < 3 or legs.max() <= 0: return None
    return float(legs[-2:].mean() / legs.max())
by = defaultdict(list)
with gzip.open(FX / "bars.psv.gz", "rt") as f:
    for r in csv.DictReader(f, delimiter="|"): by[r["eid"]].append(r)
rows = []
for r in csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"):
    rr = sorted(by[r["eid"]], key=lambda x: x["date"]); ds = [x["date"] for x in rr]
    h = np.array([float(x["h"]) for x in rr]); l = np.array([float(x["l"]) for x in rr]); D = ds.index(r["D"])
    rows.append((r["E"][:4], r["big_winner"] == "1", {N: r_c3(h, l, D, N) for N in (40, 60)}))
def era(y): return "2017-19" if y <= "2019" else ("2020-21" if y <= "2021" else "2022-23")
for N, T in ((40, 0.6), (40, 0.7), (60, 0.6)):
    print(f"swings_shrink window {N}, tight if <= {T}:")
    for e in ("2017-19", "2020-21", "2022-23"):
        g = [x for x in rows if era(x[0]) == e]; t = [x for x in g if x[2][N] is None or x[2][N] <= T]
        vals = [x[2][N] for x in g if x[2][N] is not None]
        print(f"  {e}: {len(g):3d} buys, tight {len(t):3d} ({len(t)/len(g):.0%}); median reading {np.median(vals):.2f}")
