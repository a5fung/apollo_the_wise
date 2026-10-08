"""2026-10-08 read-only: F8 rows today + which columns the sweep counts as dead (no writes: reads the audit log only)."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("F8 rows today:", await c.fetchval("""SELECT count(*) FROM mi_audit_log WHERE event_type='ep_candidate_parse_error'
              AND (created_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date"""))
        print("scan rows today:", await c.fetchval("SELECT count(*) FROM mi_ep_scan_log WHERE scan_date=(now() AT TIME ZONE 'America/New_York')::date"))
        for r in await c.fetch("SELECT summary, created_at::date d FROM mi_audit_log WHERE event_type='dead_column_detected' ORDER BY created_at"):
            t, col = r["summary"].split(".", 1)
            try:
                nn = await c.fetchval(f'SELECT count("{col}") FROM "{t}"')
            except Exception as e:
                nn = f"err {e}"
            if nn == 0:
                print("  still dead:", r["summary"], "announced", r["d"])


asyncio.run(main())
