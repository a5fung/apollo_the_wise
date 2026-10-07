"""2026-10-06 read-only: #679 failure half — any api_failure_perplexity inside a nightly theme window since 09-22,
and any theme_low_quality_description within 100 ms of one."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        fails = await c.fetch("""SELECT created_at, (created_at AT TIME ZONE 'America/New_York') t FROM mi_audit_log
                                 WHERE event_type='api_failure_perplexity' AND created_at > '2026-09-22'
                                 AND (created_at AT TIME ZONE 'America/New_York')::time BETWEEN '16:55' AND '18:30'
                                 ORDER BY created_at""")
        print("perplexity failures inside theme windows since 09-22:", len(fails))
        bad = 0
        for f in fails[:40]:
            n = await c.fetchval("""SELECT count(*) FROM mi_audit_log WHERE event_type='theme_low_quality_description'
                                    AND created_at BETWEEN $1 - interval '100 milliseconds' AND $1 + interval '100 milliseconds'""", f["created_at"])
            bad += n
            print(" ", f["t"], "caps within 100ms:", n)
        print("caps within 100ms total:", bad)


asyncio.run(main())
