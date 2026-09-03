#!/usr/bin/env python3
"""#620 fixture fix -- Alpaca SIP capture for the 6 BASELINE_DEBT names with NO mi_intraday_bars
coverage (retention starts 2026-04-13; all 6 alert dates are before that). READ-ONLY, $0 (existing
Algo Trader Plus subscription covers historical-data calls) -- writes NOTHING to any table.

Run INSIDE the market container (holds the Alpaca keys):
  ssh apollo@87.99.134.162 'docker exec -i apollo-market python -' \
      < scripts/probes/_620_fetch_bars.py > scripts/probes/_620_bars.psv

Same client construction as broker/alpaca_client.py / #617's _617_fetch_bars.py: paper keys,
DataFeed.SIP, adjustment=RAW for the minute bars (the price series the live RT overlay actually
reads), plus a RAW-vs-SPLIT daily-bar pass around each date to catch a phantom-gap-from-split
(#617's LGCL lesson) before trusting any prior close.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

_ET = ZoneInfo("America/New_York")

# (ticker, alert_date) -- the 6 fixture members with zero mi_intraday_bars coverage.
PAIRS = [
    ("STRL", date(2026, 4, 8)),
    ("ASX", date(2026, 4, 8)),
    ("NBIS", date(2026, 4, 8)),
    ("HUT", date(2026, 4, 8)),
    ("IREN", date(2026, 4, 8)),
    ("SMTC", date(2026, 3, 30)),
]


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _client() -> StockHistoricalDataClient:
    import os
    key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    sec = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    if not key or not sec:
        raise SystemExit("no ALPACA_PAPER_API_KEY / SECRET in env")
    return StockHistoricalDataClient(key, sec)


def main() -> None:
    client = _client()
    tickers = sorted({t for t, _ in PAIRS})

    print("=== MIN ===")
    print("ticker|et_min|o|h|l|c|v")
    by_day: dict[date, list[str]] = {}
    for t, d in PAIRS:
        by_day.setdefault(d, []).append(t)
    for d, syms in sorted(by_day.items()):
        start = datetime.combine(d, time(9, 25), tzinfo=_ET)
        end = datetime.combine(d, time(10, 5), tzinfo=_ET)
        req = StockBarsRequest(symbol_or_symbols=sorted(syms), timeframe=TimeFrame.Minute,
                               start=start, end=end, feed=DataFeed.SIP,
                               adjustment=Adjustment.RAW, limit=None)
        bs = client.get_stock_bars(req)
        data = bs.data if hasattr(bs, "data") else {}
        n = 0
        for sym, bars in data.items():
            for b in bars:
                ts = b.timestamp.astimezone(_ET)
                print(f"{sym}|{ts:%Y-%m-%d %H:%M}|{b.open}|{b.high}|{b.low}|{b.close}|{b.volume}")
                n += 1
        _log(f"MIN {d} {syms}: {n} bars")

    for label, adj in (("DAILY_RAW", Adjustment.RAW), ("DAILY_SPLIT", Adjustment.SPLIT)):
        print(f"=== {label} ===")
        print("ticker|trade_date|o|h|l|c|v")
        start = datetime.combine(date(2026, 3, 20), time(0, 0), tzinfo=_ET)
        end = datetime.combine(date(2026, 4, 15), time(0, 0), tzinfo=_ET)
        req = StockBarsRequest(symbol_or_symbols=tickers, timeframe=TimeFrame.Day,
                               start=start, end=end, feed=DataFeed.SIP,
                               adjustment=adj, limit=None)
        bs = client.get_stock_bars(req)
        data = bs.data if hasattr(bs, "data") else {}
        n = 0
        for sym, bars in data.items():
            for b in bars:
                ts = b.timestamp.astimezone(_ET)
                print(f"{sym}|{ts:%Y-%m-%d}|{b.open}|{b.high}|{b.low}|{b.close}|{b.volume}")
                n += 1
        _log(f"{label}: {n} rows")

    print("=== END ===")
    _log("done")


if __name__ == "__main__":
    main()
