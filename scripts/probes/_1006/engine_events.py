"""2026-10-06 read-only: the two 'failed with no page' engine events in tonight's nightly summary."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary, 400) s, LEFT(detail, 1500) d
                                  FROM mi_audit_log WHERE event_type IN ('judge_divergence_check_failed', 'stop_coverage_repair_failed')
                                  AND created_at > now() - interval '30 hours' ORDER BY created_at"""):
            print(f"{r['t']:%m-%d %H:%M:%S} {r['event_type']}\n  S: {r['s']}\n  D: {r['d']}\n")
        print("judge_divergence rows, 14 days:", [dict(r) for r in await c.fetch(
            """SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) n FROM mi_audit_log
               WHERE event_type ILIKE 'judge_divergence%' AND created_at > now() - interval '14 days' GROUP BY 1,2 ORDER BY 1""")])


asyncio.run(main())
