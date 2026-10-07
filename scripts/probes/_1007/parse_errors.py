"""2026-10-07 read-only: the 38 ep_candidate_parse_error rows (#635 F8) — what they say and when."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, LEFT(summary, 220) s, LEFT(detail, 700) d
                                FROM mi_audit_log WHERE event_type='ep_candidate_parse_error'
                                AND created_at > now() - interval '30 hours' ORDER BY created_at""")
        print("rows:", len(rows), "| first", rows[0]["t"] if rows else None, "| last", rows[-1]["t"] if rows else None)
        for r in rows[:3] + rows[-2:]:
            print(f"{r['t']:%m-%d %H:%M:%S} {r['s']}\n   {r['d']}")
        hist = await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n FROM mi_audit_log
                                WHERE event_type='ep_candidate_parse_error' GROUP BY 1 ORDER BY 1""")
        print("by day, ever:", [(str(r["d"]), r["n"]) for r in hist])


asyncio.run(main())
