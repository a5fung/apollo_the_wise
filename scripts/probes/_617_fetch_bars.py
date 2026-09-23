#!/usr/bin/env python3
"""#617 STEP 1 — capture 2 of 3: Alpaca SIP bars for the never-admitted replay set ($0: the
historical-data endpoint is covered by the existing Algo Trader Plus subscription; no per-request
charge). READ-ONLY — writes NOTHING to any table; streams gzip'd PSV to stdout.

Runs INSIDE the market container (it holds the keys; this laptop does not, and secrets are not
copied):
  python scripts/probes/_617_build_fetch.py > /tmp/_617_fetch_built.py          # embeds PAIRS
  ssh apollo@87.99.134.162 'docker exec -i apollo-market nice -n 10 python -' \
      < /tmp/_617_fetch_built.py > scripts/probes/_617_bars.psv.gz

Same client construction as broker/alpaca_client.py:182-184 (paper keys, DataFeed.SIP).
Three passes, ONE price basis for the walk (advisor 2026-09-03: never mix Alpaca raw minutes with
Polygon-adjusted mi_daily_closes in the forward walk):
  MIN          1-min RTH bars, adjustment=raw, day 0 only, grouped by date, <=50 symbols/request
  DAILY_RAW    daily bars 2026-04-15 -> 2026-09-02, adjustment=raw (the walk's forward sessions)
  DAILY_SPLIT  the same window, adjustment=split — ONLY to detect phantom gaps: a reverse split
               whose D-1 row mi_daily_closes never rewrote shows a huge 'gap' on both the capture
               and raw bars; the split-adjusted open gap is the tell (|diff| > 2pp => gap_artifact).
Timestamps are converted to ET BEFORE formatting (the .time() trap that bit on 2026-09-03).

⚠ `limit` IS A TOTAL CAP, NOT A PAGE SIZE (found 2026-09-03 by the advisor, confirmed on the first
capture): alpaca-py stops paginating once it has `limit` items across ALL pages, and the multi-
symbol response is ordered symbol-then-time — so `limit=10000` on a 50-symbol minute chunk (~19,500
bars) silently returned nothing for the alphabetical tail of every chunk (55 of 99 chunks capped at
~9,974 bars; 554 zero-bar names in chunk tails vs 39 in chunk heads). `limit=None` lets the SDK
page to completion. The first, truncated capture was discarded and every number re-derived.
"""
from __future__ import annotations

import gzip
import os
import sys
import time as _time
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

_ET = ZoneInfo("America/New_York")
PAIRS_TXT = "__PAIRS__"          # "TICKER:YYYY-MM-DD,TICKER:YYYY-MM-DD,..." (embedded by the builder)
DAILY_START, DAILY_END = date(2026, 4, 15), date(2026, 9, 2)
SYMS_PER_MIN_REQ, SYMS_PER_DAY_REQ, SLEEP_S = 50, 100, 0.25


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
        except Exception as e:  # loud-ok: retry with backoff, then skip this chunk (coverage, not silence)
            _log(f"  ! {what}: {type(e).__name__}: {str(e)[:120]} (try {k + 1}/{tries})")
            _time.sleep(2.0 * (k + 1))
    return None


def main() -> None:
    pairs = [(p.split(":")[0], date.fromisoformat(p.split(":")[1])) for p in PAIRS_TXT.split(",") if p]
    by_day: dict[date, list[str]] = defaultdict(list)
    for t, d in pairs:
        by_day[d].append(t)
    tickers = sorted({t for t, _ in pairs})
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

    for label, adj in (("DAILY_RAW", Adjustment.RAW), ("DAILY_SPLIT", Adjustment.SPLIT)):
        out.write(f"=== {label} ===\nticker|trade_date|o|h|l|c|v\n")
        n_rows = 0
        for chunk in _chunks(tickers, SYMS_PER_DAY_REQ):
            req = StockBarsRequest(symbol_or_symbols=chunk, timeframe=TimeFrame.Day,
                                   start=datetime.combine(DAILY_START, time(0, 0), tzinfo=_ET),
                                   end=datetime.combine(DAILY_END + timedelta(days=1), time(0, 0), tzinfo=_ET),
                                   feed=DataFeed.SIP, adjustment=adj, limit=None)
            bs = _get(client, req, f"{label} {len(chunk)} syms")
            n_req += 1
            _time.sleep(SLEEP_S)
            if bs is None:
                out.write(f"#FAILED_CHUNK|{label}|{','.join(chunk)}\n")
                continue
            data = bs.data if hasattr(bs, "data") else {}
            for sym, bars in data.items():
                for b in bars:
                    ts = b.timestamp.astimezone(_ET)
                    out.write(f"{sym}|{ts:%Y-%m-%d}|{b.open}|{b.high}|{b.low}|{b.close}|{b.volume}\n")
                    n_rows += 1
        _log(f"{label}: {n_rows} rows, reqs {n_req}")
    out.write("=== END ===\n")
    out.close()
    _log(f"done: {len(pairs)} pairs, {len(tickers)} tickers, {n_req} requests")


if __name__ == "__main__":
    main()
