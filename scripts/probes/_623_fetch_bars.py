"""#623 — fetch day-0 (scan_date) 1-min RTH bars from Alpaca SIP for every (ticker, scan_date)
pair in the #623 population that mi_intraday_bars does NOT already cover (<300 bars that day).
$0: the historical-data endpoint is covered by the existing Algo Trader Plus subscription.
READ-ONLY -- writes nothing to any table; streams gzip'd PSV to stdout.

Only MINUTE bars for day 0 are fetched -- `ep_replay.walk_campaign` only reads the `minutes`
dict for entry-day decisioning (ORB, stop-buy fill, same-day partial); every session AFTER day 0
walks off `daily` (mi_daily_closes, already broad -- 14,739 tickers, covers this whole population
without any Alpaca fetch). Same client construction / adjustment / feed as _617_fetch_bars.py.

Run inside the market container (holds the Alpaca keys):
  docker exec -w /app apollo-market python /tmp/_623_fetch_bars.py > _623_bars.psv.gz
"""
from __future__ import annotations

import gzip
import os
import sys
import time as _time
from collections import defaultdict
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

_ET = ZoneInfo("America/New_York")
PAIRS_TXT = "__PAIRS__"
SYMS_PER_MIN_REQ, SLEEP_S = 50, 0.25


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _client() -> StockHistoricalDataClient:
    key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    sec = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    if not key or not sec:
        raise SystemExit("no ALPACA_PAPER_API_KEY / SECRET in env")
    return StockHistoricalDataClient(key, sec)


def _chunks(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _get(client, req, what: str, tries: int = 4):
    for k in range(tries):
        try:
            return client.get_stock_bars(req)
        except Exception as e:
            _log(f"  ! {what}: {type(e).__name__}: {str(e)[:120]} (try {k + 1}/{tries})")
            _time.sleep(2.0 * (k + 1))
    return None


def main() -> None:
    pairs = [(p.split(":")[0], date.fromisoformat(p.split(":")[1])) for p in PAIRS_TXT.split(",") if p]
    by_day: dict[date, list[str]] = defaultdict(list)
    for t, d in pairs:
        by_day[d].append(t)
    client = _client()
    out = gzip.open(sys.stdout.buffer, "wt")
    n_req = 0

    out.write("=== MIN ===\nticker|et_min|o|h|l|c|v\n")
    n_bars = 0
    for d in sorted(by_day):
        syms = sorted(set(by_day[d]))
        start = datetime.combine(d, time(9, 30), tzinfo=_ET)
        end = datetime.combine(d, time(16, 0), tzinfo=_ET)
        for chunk in _chunks(syms, SYMS_PER_MIN_REQ):
            req = StockBarsRequest(symbol_or_symbols=chunk, timeframe=TimeFrame.Minute,
                                   start=start, end=end, feed=DataFeed.SIP,
                                   adjustment=Adjustment.RAW, limit=None)
            bs = _get(client, req, f"MIN {d} {len(chunk)} syms")
            n_req += 1
            _time.sleep(SLEEP_S)
            if bs is None:
                out.write(f"#FAILED_CHUNK|{d}|{','.join(chunk)}\n")
                continue
            data = bs.data if hasattr(bs, "data") else {}
            for sym, bars in data.items():
                for b in bars:
                    ts = b.timestamp.astimezone(_ET)
                    if ts.time() >= time(16, 0):
                        continue
                    out.write(f"{sym}|{ts:%Y-%m-%d %H:%M}|{b.open}|{b.high}|{b.low}|{b.close}|{b.volume}\n")
                    n_bars += 1
        _log(f"MIN {d}: {len(syms)} syms, cum bars {n_bars}, reqs {n_req}")
    out.write("=== END ===\n")
    out.close()
    _log(f"done: {len(pairs)} pairs, {n_req} requests, {n_bars} bars")


if __name__ == "__main__":
    main()
