"""2026-10-06 read-only: why the rehearsal's A2 partial exit on KO (row 410) returned False."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary, 240) s
                                  FROM mi_audit_log WHERE created_at > now() - interval '40 minutes'
                                  AND (summary ILIKE '%KO%' OR summary ILIKE '%PEP%' OR summary ILIKE '%410%' OR summary ILIKE '%411%'
                                       OR event_type ILIKE '%partial%') ORDER BY created_at LIMIT 40"""):
            print(f"{r['t']:%H:%M:%S} {r['event_type']:<36} {r['s']}")


asyncio.run(main())
