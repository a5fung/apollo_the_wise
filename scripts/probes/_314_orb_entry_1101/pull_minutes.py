"""#314 ORB entry study — the main loop's minute pull (2026-11-01), run ONCE inside apollo-market.

Follows the registration's pull contract (docs/analysis/parabolic_short_orb_entry_prereg_2026-11-01.md §6):
Alpaca v2 StockBarsRequest, feed=SIP, adjustment=RAW, 1-minute bars, each session 09:30 -> 16:00 ET (end
exclusive), every timestamp converted to ET, ts_et = the bar's START as HH:MM. One gzipped CSV
(ticker,session_date,ts_et,open,high,low,close,volume) + a sidecar meta JSON the walk gates on.
Reads minute_request.tsv only; one request per session date (all that date's tickers). Read-only: no DB, no orders.
Usage: python pull_minutes.py <minute_request.tsv> <out_dir>
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def main(req_path: str, out_dir: str) -> int:
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    sec = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    client = StockHistoricalDataClient(key, sec)

    raw = open(req_path, "rb").read()
    by_date: dict[str, set[str]] = defaultdict(set)
    for r in csv.DictReader(raw.decode().splitlines(), delimiter="\t"):
        by_date[r["session_date"]].add(r["ticker"])

    out_csv = os.path.join(out_dir, "minute_bars.csv.gz")
    n_rows, n_pairs, missing, errors = 0, 0, [], []
    with gzip.open(out_csv, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "session_date", "ts_et", "open", "high", "low", "close", "volume"])
        for i, d in enumerate(sorted(by_date)):
            y, m, dd = (int(x) for x in d.split("-"))
            start = datetime(y, m, dd, 9, 30, tzinfo=_ET)
            end = datetime(y, m, dd, 16, 0, tzinfo=_ET)
            tickers = sorted(by_date[d])
            req = StockBarsRequest(symbol_or_symbols=tickers, timeframe=TimeFrame.Minute, start=start, end=end,
                                   feed=DataFeed.SIP, adjustment=Adjustment.RAW, limit=None)
            for attempt in range(3):
                try:
                    data = client.get_stock_bars(req).data
                    break
                except Exception as e:  # loud-ok: retried, then recorded per date
                    if attempt == 2:
                        errors.append(f"{d}: {type(e).__name__}: {str(e)[:120]}")
                        data = None
                    time.sleep(2 * (attempt + 1))
            if data is None:
                continue
            for t in tickers:
                bars = data.get(t) or []
                kept = 0
                for b in bars:
                    ts = b.timestamp.astimezone(_ET)
                    if ts.date().isoformat() != d or not (start <= ts < end):
                        continue
                    w.writerow([t, d, ts.strftime("%H:%M"), b.open, b.high, b.low, b.close, int(b.volume)])
                    kept += 1
                n_rows += kept
                if kept:
                    n_pairs += 1
                else:
                    missing.append(f"{t} {d}")
            if i % 100 == 0:
                print(f"{i}/{len(by_date)} dates, {n_rows} bars, {n_pairs} pairs", flush=True)
    meta = {"feed": "sip", "adjustment": "raw", "tz": "America/New_York",
            "request_sha256": hashlib.sha256(raw).hexdigest(),
            "source": "alpaca v2 StockBarsRequest (TimeFrame.Minute), run in apollo-market by the main loop",
            "pulled_at": datetime.now(timezone.utc).isoformat()}
    with open(os.path.join(out_dir, "minute_bars.meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    with open(os.path.join(out_dir, "pull_log.txt"), "w") as f:
        f.write(f"dates {len(by_date)} | pairs requested {sum(len(v) for v in by_date.values())} | pairs with bars "
                f"{n_pairs} | bars {n_rows} | date errors {len(errors)}\n")
        f.write("ERRORS\n" + "\n".join(errors) + "\nMISSING (no bar in the session)\n" + "\n".join(missing) + "\n")
    print(open(os.path.join(out_dir, "pull_log.txt")).read().splitlines()[0])
    return 0 if not errors else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
