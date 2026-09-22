"""#545 Phase 2 -- fetch day-0 1-min RTH bars from Alpaca SIP for the deduped `stop_too_wide`
refusal survivors that are ABSENT from P-REPLAY (pre-05-11 or post-08-28, so never captured
by the #623/#545 pulls), plus BAND/STRL/EVER/TTMI named explicitly in the design doc's §5.1.
Same client construction / adjustment / feed as _623_fetch_bars.py -- $0, Algo Trader Plus
SIP subscription already covers this endpoint. READ-ONLY: writes nothing to any table.

Population (derived from the 2026-09-22 dedupe probe on mi_live_trades, magna53 only, deduped
strategies dropped): 8 ticker-days absent from P-REPLAY (the other 8 of the 16 magna53 refusals
are already captured in scripts/ep_replay_data/ and need no fetch):
  TLRY 2026-04-23, WST 2026-04-23, WKC 2026-04-24, BAND 2026-04-30, TTMI 2026-04-30,
  EVER 2026-05-05, STRL 2026-05-05, ROIV 2026-09-08

Run inside the market container (holds the Alpaca keys):
  docker exec apollo-market python3 /tmp/_545p2_fetch_bars.py > _545p2_bars.psv.gz
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
PAIRS_TXT = ("TLRY:2026-04-23,WST:2026-04-23,WKC:2026-04-24,BAND:2026-04-30,"
             "TTMI:2026-04-30,EVER:2026-05-05,STRL:2026-05-05,ROIV:2026-09-08")
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
