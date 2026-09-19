"""Verify VECO 4/21-5/07 prices against Polygon directly vs mi_daily_closes.

Settles the question: was yesterday's data (showing 5/7 as the +39% gap day)
or today's data (5/6 as +25% gap, 5/7 down -7%) correct?
"""
import asyncio
import datetime
import sys

sys.path.insert(0, "/app")

from agents.market_intelligence.collector import _polygon_get
from agents.market_intelligence.db import get_pool


async def main():
    # Pull from Polygon directly with adjusted=true (what splits_ingest sees)
    data = await _polygon_get(
        f"/v2/aggs/ticker/VECO/range/1/day/2026-04-21/2026-05-08",
        {"adjusted": "true", "sort": "asc", "limit": 50},
    )
    polygon_bars = data.get("results") or []
    print(f"=== Polygon adjusted=true ({len(polygon_bars)} bars) ===")
    print(f"{'date':<12} {'open':>7} {'high':>7} {'low':>7} {'close':>7} {'volume':>10}")
    for b in polygon_bars:
        ts = datetime.datetime.fromtimestamp(b["t"] / 1000, tz=datetime.timezone.utc).date()
        print(f"{ts.isoformat():<12} {b['o']:>7.2f} {b['h']:>7.2f} {b['l']:>7.2f} {b['c']:>7.2f} {int(b['v']):>10d}")

    # And unadjusted (raw, as-traded)
    data_unadj = await _polygon_get(
        f"/v2/aggs/ticker/VECO/range/1/day/2026-04-21/2026-05-08",
        {"adjusted": "false", "sort": "asc", "limit": 50},
    )
    unadj_bars = data_unadj.get("results") or []
    print(f"\n=== Polygon adjusted=false ({len(unadj_bars)} bars) ===")
    print(f"{'date':<12} {'open':>7} {'high':>7} {'low':>7} {'close':>7} {'volume':>10}")
    for b in unadj_bars:
        ts = datetime.datetime.fromtimestamp(b["t"] / 1000, tz=datetime.timezone.utc).date()
        print(f"{ts.isoformat():<12} {b['o']:>7.2f} {b['h']:>7.2f} {b['l']:>7.2f} {b['c']:>7.2f} {int(b['v']):>10d}")

    # And what's in mi_daily_closes
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT trade_date, open_price, high_price, low_price, close, volume
            FROM mi_daily_closes
            WHERE ticker='VECO' AND trade_date BETWEEN '2026-04-21' AND '2026-05-07'
            ORDER BY trade_date
            """
        )
    print(f"\n=== mi_daily_closes ({len(rows)} bars) ===")
    print(f"{'date':<12} {'open':>7} {'high':>7} {'low':>7} {'close':>7} {'volume':>10}")
    for r in rows:
        print(
            f"{r['trade_date'].isoformat():<12} "
            f"{r['open_price']:>7.2f} {r['high_price']:>7.2f} "
            f"{r['low_price']:>7.2f} {r['close']:>7.2f} {int(r['volume']):>10d}"
        )


if __name__ == "__main__":
    asyncio.run(main())
