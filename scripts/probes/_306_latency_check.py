"""#306 pre-step — Monday RTH latency probe (read-only, ~30 lines).

Compares Polygon vs Alpaca minute-bar lag for a liquid ticker (SPY) during market
hours, to confirm the #306 intraday path recorder's premise: Polygon's Starter-plan
minute bars run ~15-17 min delayed, real-time Alpaca does not. Prints `now_et` minus
the newest bar's timestamp for each feed.

Run (during RTH — market closed as of authoring, so this is UNRUN; ready for Monday):
    ssh apollo@87.99.134.162 'docker exec apollo-market python -m scripts.probes._306_latency_check'

Run from apollo-market specifically: both containers hold Alpaca keys, but only
apollo-market holds Polygon creds, so one `docker exec` covers both feeds.

Read-only: fetches only (collector.get_minute_bars / Alpaca get_stock_bars), no writes,
no order calls.

Expected (docs/design/306_intraday_path_recorder_2026-07-25.md §1): Polygon lag
~= 15-17 min; Alpaca lag <= ~1-2 min (prod ALPACA_DATA_FEED=sip verified on both
containers). If Polygon is NOT delayed, the design stands unchanged (defect #2 —
open-only selection — still fully explains the sub-5-minute blindness; say so in the
ship note). If Alpaca is materially delayed (> ~3 min): STOP, do not ship #306 as
designed — report back instead.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
TICKER = "SPY"


async def _polygon_lag(now_et: datetime) -> str:
    from agents.market_intelligence.collector import get_minute_bars
    today = now_et.date().isoformat()
    bars = await get_minute_bars(TICKER, today, today)
    if not bars:
        return "Polygon: no bars returned"
    newest_ms = max(int(b["t"]) for b in bars if b.get("t"))
    newest_dt = datetime.fromtimestamp(newest_ms / 1000, tz=timezone.utc).astimezone(_ET)
    lag = now_et - newest_dt
    return f"Polygon:  newest bar {newest_dt:%H:%M:%S} ET, lag = {lag}"


def _alpaca_lag(now_et: datetime) -> str:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from agents.market_intelligence.broker.alpaca_client import _get_data_client, get_data_feed

    client = _get_data_client()
    feed = get_data_feed()
    start = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    request = StockBarsRequest(
        symbol_or_symbols=TICKER, timeframe=TimeFrame.Minute,
        start=start, end=now_et, feed=feed,
    )
    bars = client.get_stock_bars(request)
    bar_data = bars.data if hasattr(bars, "data") else bars
    bar_set = bar_data.get(TICKER, []) or []
    if not bar_set:
        return "Alpaca:   no bars returned"
    newest_dt = max(b.timestamp for b in bar_set).astimezone(_ET)
    lag = now_et - newest_dt
    return f"Alpaca ({feed}): newest bar {newest_dt:%H:%M:%S} ET, lag = {lag}"


async def main() -> int:
    now_et = datetime.now(_ET)
    print(f"#306 latency probe — {TICKER} @ {now_et:%Y-%m-%d %H:%M:%S} ET\n")
    print(await _polygon_lag(now_et))
    print(_alpaca_lag(now_et))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
