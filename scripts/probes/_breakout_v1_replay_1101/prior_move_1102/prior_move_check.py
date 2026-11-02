"""11-02 follow-up to his CODX/PENN charts: on the bars, MTW 10-30 does NOT look worse than CODX-1 / PENN-2 on his two stated
reasons once measured in each stock's own daily range (scripts/probes/_his_charts_1102/three_way.out). What does differ is SIZE:
the daily range (already floored at 4.26% today) and the run before the base (MTW +30.8%, v1's bar 30%). This reads, $0 and
read-only on the frozen replay: (1) the prior move of the 12 of Qullamaggie's 24 graded setups v1 catches; (2) floor-kept trades
by prior-move band (no slot limit, 2c, both eras). DESCRIPTIVE — no threshold is chosen here (a list-criterion change is his)."""
import sys, gzip, csv
from pathlib import Path
import numpy as np
P = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(P)); sys.path.insert(0, str(P / "followup_tests_1101"))
import followup as F

FLOOR = 0.0426
rows = F.load_placed()
print("placed row keys:", sorted(rows[0].keys())[:40])
pm = {}
for era in ("A", "B"):
    with gzip.open(P / "out" / f"list_era{era}.tsv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            pm[(r["scan_date"], r["ticker"])] = float(r["prior_move"])
QM12 = (("CELH-1", "CELH", "2020-06-22"), ("CELH-3", "CELH", "2020-08-04"), ("CODX-1", "CODX", "2020-04-15"), ("LVGO-4", "LVGO", "2020-07-02"),
        ("OPK-2", "OPK", "2020-07-16"), ("OSTK-2", "NXH", "2020-06-22"), ("SRNE-2", "SRNE", "2020-07-30"), ("PRTS", "PRTS", "2020-07-07"),
        ("ARCT", "ARCT", "2020-07-10"), ("HL", "HL", "2020-08-03"), ("IBIO-1", "IBIO", "2020-07-14"), ("PENN-2", "PENN", "2020-06-22"))
print("\n(1) prior move of the 12 of Qullamaggie's graded setups v1 catches (list row at the catching watch night):")
vals = []
for name, t, d in QM12:
    v = pm.get((d, t)); vals.append(v)
    print(f"  {name:7s} {d}  prior move {('%+.0f%%' % (100 * v)) if v is not None else 'NOT ON LIST'}")
print("  MTW 10-30 (his NO): +31%")
kept = [t for t in rows if t["adr20"] is not None and float(t["adr20"]) >= FLOOR and t["filled"] and t["decisive"] and t["r_2c"] is not None]
print(f"\n(2) floor-kept filled decisive trades (no slot limit, 2c) by prior-move band; joined {sum((str(t['D']), t['ticker']) in pm for t in kept)} of {len(kept)}")
BANDS = ((0.30, 0.40), (0.40, 0.50), (0.50, 0.75), (0.75, 1.00), (1.00, 2.00), (2.00, 1e9))
for era in ("2017-21", "2022-24", None):
    print(f"  era {era or 'both'}")
    for lo, hi in BANDS:
        r = np.array([t["r_2c"] for t in kept if (era is None or t["era"] == era) and lo <= pm.get((str(t["D"]), t["ticker"]), -1) < hi])
        if len(r):
            print(f"    {int(lo*100):4d}%-{'' if hi > 1e8 else int(hi*100)}%{'+' if hi > 1e8 else ''}  n {len(r):5d}  mean {r.mean():+.3f}  win {np.mean(r>0):.1%}  3R+ {np.mean(r>=3):.1%}  10R+/100 {100*np.mean(r>=10):.1f}")
