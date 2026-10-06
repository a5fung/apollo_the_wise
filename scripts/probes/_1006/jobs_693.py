"""2026-10-06 read-only: #693 — the four theme jobs' run events and errors, Mon + Tue nights; last synthesis run."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) n
                                  FROM mi_audit_log WHERE created_at > now() - interval '3 days'
                                  AND (event_type ILIKE '%synthesis%' OR event_type ILIKE '%narrative%' OR event_type ILIKE '%validation_run%'
                                       OR event_type ILIKE 'theme_validation%' OR event_type ILIKE '%discovery_run%' OR event_type ILIKE '%parent_pass%')
                                  GROUP BY 1,2 ORDER BY 1,2"""):
            print(dict(r))
        print("last theme_synthesis_run:", await c.fetchval(
            "SELECT max(created_at AT TIME ZONE 'America/New_York') FROM mi_audit_log WHERE event_type='theme_synthesis_run'"))
        for r in await c.fetch("""SELECT caller, (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n, max(stop_reason) sr,
                                  round(avg(output_tokens)) avg_out
                                  FROM api_usage WHERE created_at > now() - interval '3 days'
                                  AND caller IN ('theme_validation','theme_synthesis','theme_discovery','narrative_theme_discovery','theme_parent_pass','theme_containment')
                                  GROUP BY 1,2 ORDER BY 1,2"""):
            print("  usage", dict(r))


asyncio.run(main())
