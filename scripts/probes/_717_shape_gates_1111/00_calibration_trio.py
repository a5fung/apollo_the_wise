"""CALIBRATION ONLY (declared in docs/analysis/cb_shape_gates_2026-11-11.md, Calibration): the five shape gates on the
three charts the operator read in his own words on 2026-11-02 — CODX-1 (D 2020-04-15) and PENN-2 (D 2020-06-22), which
"fit perfectly" (higher lows, surfing the 10/20), and MTW (D 2026-10-30), "not a breakout". Reads ONLY those three
series (CODX / PENN bars from the scorecard fixture's file, at nights that are NOT scored rows; MTW from mtw_bars.csv).
Run from the repo root:
    python3 scripts/probes/_717_shape_gates_1111/00_calibration_trio.py > scripts/probes/_717_shape_gates_1111/00_calibration_trio.out
"""
import csv
import gzip
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402

FX = Path("tests/fixtures/qm_breakout_scorecard")
want = {"731": ("CODX-1 (QM good; his 'fit perfectly')", date(2020, 4, 15)),
        "1265": ("PENN-2 (QM good; his 'fit perfectly')", date(2020, 6, 22))}
rows = {k: [] for k in want}
with gzip.open(FX / "bars.psv.gz", "rt") as f:
    for r in csv.DictReader(f, delimiter="|"):
        if r["eid"] in rows:
            rows[r["eid"]].append(r)
cases = []
for eid, (name, D) in want.items():
    rr = sorted(rows[eid], key=lambda x: x["date"])
    ds = [date.fromisoformat(x["date"]) for x in rr]
    cases.append((name, cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rr] for k in "ohlcv"]), D))
m = list(csv.DictReader(open(FX / "mtw_bars.csv")))
cases.append(("MTW 10-30 (his 'not a breakout')", cb.daily_bars_from_arrays(
    [date.fromisoformat(x["trade_date"]) for x in m],
    *[[float(x[k]) for x in m] for k in ("open_price", "high_price", "low_price", "close", "volume")]), date(2026, 10, 30)))
for name, b, D in cases:
    i = b.dates.index(D)
    g = bv.v1_gates(b, i, rs_best=99.0)
    sg = bv.shape_gates(b, i, P=g["pole_idx"], adr20=g["adr20"])
    print(f"\n{name}  D {D}  pole {g['pole_date']}  base {i - g['pole_idx']} sessions  ADR20 {g['adr20']:.1%}  "
          f"existing gates failed: {g['failed']}")
    for k in bv.SHAPE_GATES:
        print(f"  {k:13s} {'PASS' if sg[k]['pass'] else 'FAIL'}  {json.dumps(sg[k]['value'])}")
