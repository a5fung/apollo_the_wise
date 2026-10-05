"""2026-10-05 read-only: the latest last_eval in the coil table (the board filters on it)."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print(await c.fetchrow("SELECT max(last_eval)::text mx, count(*) FILTER (WHERE last_eval=(SELECT max(last_eval) FROM mi_anticipation_consolidation)) n FROM mi_anticipation_consolidation"))


asyncio.run(main())
