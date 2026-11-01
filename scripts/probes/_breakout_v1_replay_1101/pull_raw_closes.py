"""C (breakout v1 paper-baseline replay) — the raw-close pull (2026-11-01), run ONCE in apollo-market by the main loop.

The registration's §7 pull 2: UNADJUSTED daily closes for the tickers in raw_close_request.tsv (ticker, first_date,
last_date), dates <= 2024-12-31 only, from Alpaca daily bars with adjustment=RAW. Output: a headerless gzip CSV
`ticker,date,raw_close` + a sidecar meta JSON naming the request's sha256. Read-only market data; no DB, no orders.
Usage: python pull_raw_closes.py <raw_close_request.tsv> <out_dir>
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_SEAL = date(2024, 12, 31)


def main(req_path: str, out_dir: str) -> int:
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    sec = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    client = StockHistoricalDataClient(key, sec)
    raw = open(req_path, "rb").read()
    rows = [r for r in csv.reader(raw.decode().splitlines(), delimiter="\t") if r and r[0] != "ticker"]
    n, empty, errors = 0, [], []
    with gzip.open(os.path.join(out_dir, "raw_close_bv1_1101.csv.gz"), "wt", newline="") as f:
        w = csv.writer(f)
        for t, first, last in (r[:3] for r in rows):
            d0 = date.fromisoformat(first)
            d1 = min(date.fromisoformat(last), _SEAL)
            req = StockBarsRequest(symbol_or_symbols=t, timeframe=TimeFrame.Day,
                                   start=datetime(d0.year, d0.month, d0.day, tzinfo=_ET),
                                   end=datetime(d1.year, d1.month, d1.day, tzinfo=_ET) + timedelta(days=1),
                                   feed=DataFeed.SIP, adjustment=Adjustment.RAW, limit=None)
            try:
                bars = client.get_stock_bars(req).data.get(t) or []
            except Exception as e:  # loud-ok: recorded per ticker
                errors.append(f"{t}: {type(e).__name__}: {str(e)[:120]}")
                continue
            kept = 0
            for b in bars:
                d = b.timestamp.astimezone(_ET).date()
                if d0 <= d <= d1:
                    w.writerow([t, d.isoformat(), b.close])
                    kept += 1
            n += kept
            if not kept:
                empty.append(t)
    meta = {"adjustment": "raw", "feed": "sip", "request_sha256": hashlib.sha256(raw).hexdigest(),
            "source": "alpaca v2 StockBarsRequest (TimeFrame.Day), run in apollo-market by the main loop",
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
