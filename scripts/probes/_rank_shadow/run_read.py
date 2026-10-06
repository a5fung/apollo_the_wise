"""Run the alert-rank out-of-sample read's pinned SQL (scripts/probes/_verify_rank_shadow_2026-09-21.sql)
read-only and print pipe-separated rows (the same shape as the earlier .out files)."""
import asyncio, sys
from agents.market_intelligence.db import get_pool


async def main():
    sql = open(sys.argv[1]).read()
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch(sql)
    if rows:
        print("|".join(rows[0].keys()))
    for r in rows:
        print("|".join("" if v is None else str(v) for v in r.values()))


asyncio.run(main())
