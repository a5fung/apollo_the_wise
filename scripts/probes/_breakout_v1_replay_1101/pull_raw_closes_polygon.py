"""C — the raw-close pull, re-made from Polygon (2026-11-01, main loop, his "Allow"; registration §7 pull 2 allows
Polygon adjusted=false). WHY: Alpaca maps a symbol to its CURRENT owner, so for a reused symbol (ARIS, TEN, CNR ...)
it returned another company's prices (the raw/adjusted ratio drifted instead of holding a clean split constant); Polygon's
aggregates are point-in-time by ticker. Single source for every ticker. Dates <= 2024-12-31 only. Output: headerless gzip
CSV `ticker,date,raw_close` + sidecar meta (request_sha256 of raw_close_request.tsv). Read-only market data.
Usage: python pull_raw_closes_polygon.py <raw_close_request.tsv> <out_dir>
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_SEAL = date(2024, 12, 31)


def main(req_path: str, out_dir: str) -> int:
    key = os.environ.get("POLYGON_API_KEY", "")
    raw = open(req_path, "rb").read()
    rows = [r for r in csv.reader(raw.decode().splitlines(), delimiter="\t") if r and r[0] != "ticker"]
    n, empty, errors = 0, [], []
    with gzip.open(os.path.join(out_dir, "raw_close_bv1_1101.csv.gz"), "wt", newline="") as f:
        w = csv.writer(f)
        for t, first, last in (r[:3] for r in rows):
            d1 = min(date.fromisoformat(last), _SEAL)
            url = (f"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/day/{first}/{d1.isoformat()}"
                   f"?adjusted=false&sort=asc&limit=50000&apiKey={key}")
            for attempt in range(3):
                try:
                    data = json.loads(urllib.request.urlopen(url, timeout=60).read())
                    break
                except Exception as e:  # loud-ok: retried, then recorded per ticker
                    data = None
                    if attempt == 2:
                        errors.append(f"{t}: {type(e).__name__}: {str(e)[:100]}")
                    time.sleep(2 * (attempt + 1))
            if data is None:
                continue
            kept = 0
            for b in data.get("results") or []:
                d = datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).astimezone(_ET).date()
                if d <= _SEAL:
                    w.writerow([t, d.isoformat(), b["c"]])
                    kept += 1
            n += kept
            if not kept:
                empty.append(t)
            time.sleep(0.15)
    meta = {"adjustment": "raw", "feed": "polygon v2 aggs adjusted=false", "request_sha256": hashlib.sha256(raw).hexdigest(),
            "source": "polygon v2 aggregates (1 day, adjusted=false), point-in-time by ticker; run in apollo-market by the main loop; "
                      "replaces the first Alpaca pull (symbol reuse returned other companies' prices)",
            "pulled_at": datetime.now(timezone.utc).isoformat()}
    with open(os.path.join(out_dir, "raw_close_bv1_1101.meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    with open(os.path.join(out_dir, "raw_close_pull_log.txt"), "w") as f:
        f.write(f"tickers {len(rows)} | rows {n} | empty {len(empty)} | errors {len(errors)}\n")
        f.write("EMPTY\n" + "\n".join(empty) + "\nERRORS\n" + "\n".join(errors) + "\n")
    print(open(os.path.join(out_dir, "raw_close_pull_log.txt")).read().splitlines()[0])
    return 0 if not errors else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
