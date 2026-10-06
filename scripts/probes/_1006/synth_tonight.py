"""2026-10-06 read-only: #693 — did tonight's theme synthesis run, and with what result (both nights)."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary, 300) s, LEFT(detail, 400) d
                                  FROM mi_audit_log WHERE event_type ILIKE 'theme_synthesis%' AND created_at > now() - interval '3 days'
                                  ORDER BY created_at"""):
            print(f"{r['t']:%m-%d %H:%M} {r['event_type']} | {r['s']} | {r['d']}")
        for r in await c.fetch("""SELECT job_id, status, started_at AT TIME ZONE 'America/New_York' t, error_message
                                  FROM mi_job_runs WHERE started_at > now() - interval '3 days' AND job_id ILIKE '%synth%' ORDER BY started_at"""):
            print(dict(r))


asyncio.run(main())
