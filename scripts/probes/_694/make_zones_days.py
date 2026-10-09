#!/usr/bin/env python3
"""#694 — which days get key 5 (zones cleared), and the q10_daily.sql ticker list. Run BEFORE the
q10 pull (it was, once). Days = every crowded morning (last pre-open pool > 20) + every day whose
pool holds a labelled real EP (MUST_NOT_MISS, alert_date >= 2026-04-13). Local, no network."""
import csv
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS  # noqa: E402

rows = [r for r in csv.DictReader(open(HERE / "q03_pool.out"), delimiter="|") if r["ticker"]]
n = Counter(r["scan_date"] for r in rows)
crowded = {d for d, c in n.items() if c > 20}
pooled = {(r["ticker"], r["scan_date"]) for r in rows}
posdays = {m.alert_date for m in MUST_NOT_MISS if (m.ticker, m.alert_date) in pooled}
days = sorted(crowded | posdays)
(HERE / "zones_days.txt").write_text("\n".join(days) + "\n")
tick = sorted({r["ticker"] for r in rows if r["scan_date"] in days})
print(f"{len(days)} days ({len(crowded)} crowded, {len(posdays)} with a pooled real EP); {len(tick)} tickers")
