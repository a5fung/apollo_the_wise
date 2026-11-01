"""C — fill the raw-close gaps the Alpaca pull left (2026-11-01, main loop, his "Allow"): INBX (0 rows from Alpaca — the
symbol now names a 2024 spin-off) and ARIS (5 dates). The registration's §7 pull 2 allows Polygon adjusted=false.
Polygon v2 daily aggregates, adjusted=false, dates <= 2024-12-31 only; appends `ticker,date,raw_close` rows for
(ticker, date) pairs the Alpaca file lacks. Read-only market data. Usage: python pull_raw_gaps_polygon.py <in.csv.gz> <out.csv.gz>
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
GAPS = {"INBX": ("2022-07-15", "2024-02-22"), "ARIS": ("2022-06-21", "2024-12-03")}


def main(src: str, dst: str) -> int:
    key = os.environ.get("POLYGON_API_KEY", "")
    have = set()
    rows = []
    for t, d, c in csv.reader(gzip.open(src, "rt")):
        have.add((t, d)); rows.append((t, d, c))
    added = {}
    for t, (d0, d1) in GAPS.items():
        url = (f"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/day/{d0}/{min(d1, '2024-12-31')}"
               f"?adjusted=false&sort=asc&limit=50000&apiKey={key}")
        data = json.loads(urllib.request.urlopen(url, timeout=60).read())
        n = 0
        for b in data.get("results") or []:
            d = datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).astimezone(_ET).date()
            if d > date(2024, 12, 31) or (t, d.isoformat()) in have:
                continue
            rows.append((t, d.isoformat(), b["c"])); n += 1
        added[t] = n
    rows.sort()
    with gzip.open(dst, "wt", newline="") as f:
        csv.writer(f).writerows(rows)
    print(json.dumps({"added": added, "rows_total": len(rows)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
