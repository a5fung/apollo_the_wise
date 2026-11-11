"""Round 2 DIAGNOSIS (exploratory, in-sample — feeds amendment 2, declared there): WHY the three structure gates block
Qullamaggie's buys, and which night-before measures separate his 17 `no` from his 11 good/ok WITHOUT blocking them.
Bars <= D only (the buy day E is cut off). Prints a feature table for both populations + quantiles.
    python3 scripts/probes/_717_shape_gates_1111/04_diagnose.py > scripts/probes/_717_shape_gates_1111/04_diagnose.out"""
import csv
import gzip
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402
from tests.fixtures.breakout_list_grades import BREAKOUT_LIST_GRADES  # noqa: E402


def feats(b, D, v):
    h, l, c = (np.asarray(x, float) for x in (b.h, b.l, b.c))
    adr = v["adr20"]
    P = v["pole_idx"]
    e10, e21 = bv.ema_series(c, D, 10), bv.ema_series(c, D, 21)
    sma = lambda n, i: float(c[i - n + 1:i + 1].mean())
    B = P + 1 + int(np.argmin(l[P + 1:D + 1]))
    x = np.arange(10)
    f = {
        "base_len": D - P, "since_bottom": D - B,
        "bottom_depth_adr": (h[P] - l[B]) / h[P] / adr,
        "de10_5": (e10[D] / e10[D - 5] - 1) / adr, "de21_5": (e21[D] / e21[D - 5] - 1) / adr,
        "de21_10": (e21[D] / e21[D - 10] - 1) / adr, "de21_20": (e21[D] / e21[D - 20] - 1) / adr,
        "dsma50_10": (sma(50, D) / sma(50, D - 10) - 1) / adr,
        "e10_vs_e21": (e10[D] / e21[D] - 1) / adr, "e21_vs_s50": (e21[D] / sma(50, D) - 1) / adr,
        "c_vs_e10": (c[D] / e10[D] - 1) / adr, "c_vs_e21": (c[D] / e21[D] - 1) / adr, "c_vs_s50": (c[D] / sma(50, D) - 1) / adr,
        "max10_vs_s50": (c[D - 9:D + 1].max() / sma(50, D) - 1) / adr,
        "lowslope10": np.polyfit(x, l[D - 9:D + 1], 1)[0] / c[D] / adr,       # daily ranges per session
        "highslope10": np.polyfit(x, h[D - 9:D + 1], 1)[0] / c[D] / adr,
        "low5_vs_prev5": (l[D - 4:D + 1].min() / l[D - 9:D - 4].min() - 1) / adr,
        "low5_vs_prev10": (l[D - 4:D + 1].min() / l[D - 14:D - 4].min() - 1) / adr,
        "low3_vs_prev7": (l[D - 2:D + 1].min() / l[D - 9:D - 2].min() - 1) / adr,
        "c_vs_basehigh": (c[D] / h[P] - 1) / adr,
        "run20": (c[D] / c[D - 20] - 1) / adr, "run10": (c[D] / c[D - 10] - 1) / adr,
        "spread10": (c[D - 9:D + 1].max() / c[D - 9:D + 1].min() - 1) / adr,
        "pos_in_base": (c[D] - l[B]) / max(h[P] - l[B], 1e-9),
    }
    return f


rowsG, rowsQ = [], []
gb = defaultdict(list)
with gzip.open("tests/fixtures/breakout_list_grades_bars.psv.gz", "rt") as fh:
    for r in csv.DictReader(fh, delimiter="|"):
        gb[(r["ticker"], r["list_date"])].append(r)
for g in BREAKOUT_LIST_GRADES:
    rr = gb[(g.ticker, g.list_date)]
    b = cb.daily_bars_from_arrays([date.fromisoformat(x["date"]) for x in rr], *[[float(x[k]) for x in rr] for k in "ohlcv"])
    D = len(b) - 1
    v = bv.v1_gates(b, D, rs_best=99.0)
    sg = bv.shape_gates(b, D, P=v["pole_idx"], adr20=v["adr20"])
    rowsG.append((f"{g.ticker}", g.grade, [k for k in bv.SHAPE_GATES if not sg[k]["pass"]], feats(b, D, v)))
FX = Path("tests/fixtures/qm_breakout_scorecard")
by = defaultdict(list)
with gzip.open(FX / "bars.psv.gz", "rt") as fh:
    for r in csv.DictReader(fh, delimiter="|"):
        by[r["eid"]].append(r)
for r in csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"):
    rr = sorted(by[r["eid"]], key=lambda x: x["date"])
    D = [x["date"] for x in rr].index(r["D"])
    rr = rr[:D + 1]
    b = cb.daily_bars_from_arrays([date.fromisoformat(x["date"]) for x in rr], *[[float(x[k]) for x in rr] for k in "ohlcv"])
    v = bv.v1_gates(b, D, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))
    if not v["ok"]:
        continue
    sg = bv.shape_gates(b, D, P=v["pole_idx"], adr20=v["adr20"])
    rowsQ.append((f"{r['sym']} {r['E']}", ("BIG " if r["big_winner"] == "1" else "") + (r["his_label"] or "-"),
                  [k for k in bv.SHAPE_GATES if not sg[k]["pass"]], feats(b, D, v)))

keys = list(rowsG[0][3])
print("=== HIS GRADES (n = 29) ===")
print(f"{'name':18s}{'grade':13s}" + "".join(f"{k[:11]:>12s}" for k in keys) + "  fails")
for n, gr, fl, f in sorted(rowsG, key=lambda x: x[1]):
    print(f"{n:18s}{gr:13s}" + "".join(f"{f[k]:12.2f}" for k in keys) + f"  {fl}")
print("\n=== QULLAMAGGIE'S LISTED BUYS (n = 263): quantiles of each measure ===")
print(f"{'measure':18s}" + "".join(f"{q:>9s}" for q in ("min", "p1", "p2", "p5", "p10", "p25", "p50", "p75", "p90", "p95", "p98", "p99", "max")))
for k in keys:
    a = np.array([f[k] for *_, f in rowsQ])
    print(f"{k:18s}" + "".join(f"{np.percentile(a, q):9.2f}" for q in (0, 1, 2, 5, 10, 25, 50, 75, 90, 95, 98, 99, 100)))
print("\n=== same, BIG WINNERS only (n = 26) ===")
for k in keys:
    a = np.array([f[k] for n, lab, fl, f in rowsQ if lab.startswith("BIG")])
    print(f"{k:18s}" + "".join(f"{np.percentile(a, q):9.2f}" for q in (0, 5, 10, 25, 50, 75, 90, 95, 100)))
print("\n=== QM buys blocked by a structure gate (higher_lows / no_lower_low / rising_avg), row by row ===")
print(f"{'name':18s}{'label':22s}" + "".join(f"{k[:11]:>12s}" for k in keys) + "  fails")
for n, lab, fl, f in rowsQ:
    if set(fl) & {"higher_lows", "no_lower_low", "rising_avg"}:
        print(f"{n:18s}{lab[:21]:22s}" + "".join(f"{f[k]:12.2f}" for k in keys) + f"  {fl}")
