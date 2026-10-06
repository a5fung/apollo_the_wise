"""2026-10-06 read-only: can #624's rule be replayed on history? Universe coverage of mi_daily_closes over time,
and how many day-rows would pass the price-only half of the rule (prev close >= $5, open gap >= 15%)."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("""SELECT date_trunc('quarter', trade_date)::date q, count(DISTINCT ticker) tickers, count(DISTINCT trade_date) days
                                  FROM mi_daily_closes WHERE trade_date >= '2023-01-01' GROUP BY 1 ORDER BY 1"""):
            print(dict(r))
        n = await c.fetchrow("""WITH x AS (
              SELECT ticker, trade_date, open_price, volume,
                     lag(close) OVER (PARTITION BY ticker ORDER BY trade_date) pc
              FROM mi_daily_closes WHERE trade_date >= '2023-12-01')
            SELECT count(*) FILTER (WHERE pc >= 5 AND open_price >= pc * 1.15 AND trade_date >= '2024-01-01') gap15,
                   count(DISTINCT ticker) FILTER (WHERE pc >= 5 AND open_price >= pc * 1.15 AND trade_date >= '2024-01-01') names
            FROM x""")
        print("price-only candidates since 2024-01-01:", dict(n))


asyncio.run(main())
