import asyncio
from agents.market_intelligence.db import get_pool
async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n FROM mi_audit_log
             WHERE event_type='ticker_revalidated_out' AND created_at > '2026-09-14' GROUP BY 1 ORDER BY 1"""):
            print(r['d'], r['n'])
asyncio.run(main())
