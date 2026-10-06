"""2026-10-05 read-only after the 21:15 deploy: #687 positive checks — the 19:01 depth_open_auction_sale
run and the 16:45 close-below job each left their own row today."""
import asyncio
from agents.market_intelligence.db import get_pool

T = "created_at >= (date_trunc('day', now() AT TIME ZONE 'America/New_York') AT TIME ZONE 'America/New_York')"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch(f"""SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary, 200) s
                                   FROM mi_audit_log WHERE {T} AND (event_type ILIKE '%depth%' OR summary ILIKE '%depth_open_auction%'
                                   OR summary ILIKE '%close_below%' OR summary ILIKE '%close-below%' OR event_type ILIKE '%close_below%'
                                   OR (event_type ILIKE 'job%' AND (summary ILIKE '%16:45%' OR summary ILIKE '%19:01%')))
                                   ORDER BY created_at"""):
            print(f"  {r['t']:%H:%M:%S} {r['event_type']:<32} {r['s']}")
        for r in await c.fetch("""SELECT job_id, status, started_at AT TIME ZONE 'America/New_York' t, LEFT(coalesce(error,''),120) e
                                  FROM mi_job_runs WHERE started_at > now() - interval '8 hours'
                                  AND (job_id ILIKE '%depth%' OR job_id ILIKE '%close_below%' OR job_id ILIKE '%eod_exit%')
                                  ORDER BY started_at""") if await c.fetchval("SELECT to_regclass('mi_job_runs')") else []:
            print("  JOB", dict(r))


asyncio.run(main())
