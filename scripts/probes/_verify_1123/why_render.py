import asyncio, datetime
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.agent import _why_score_block
async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        await c.execute("SET default_transaction_read_only = on")
    for t in ("EROK",):
        lines = await _why_score_block(pool, t, datetime.date(2026, 11, 23))
        print(f"== {t}"); print("\n".join(lines))
asyncio.run(main())
