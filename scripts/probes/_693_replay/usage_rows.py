import asyncio, json
from agents.market_intelligence.db import get_pool
async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::text t, input_tokens i, output_tokens o, stop_reason s
             FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-05' ORDER BY created_at""")
    json.dump([dict(r) for r in rows], open('/tmp/693_usage_1005.json','w'))
    import collections
    b = collections.Counter(r['t'][11:15] for r in rows)
    print(sorted(b.items()))
asyncio.run(main())
