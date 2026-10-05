"""2026-10-05 read-only: of every column the dead-column sweep ever flagged, which are populated NOW
(i.e. the flag was a not-yet-run writer, not a dead column) and how soon after the flag the first
value landed (only knowable where the table has a timestamp column)."""
import asyncio
from agents.market_intelligence.db import get_pool

T = "AT TIME ZONE 'America/New_York'"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch(f"""SELECT summary, (created_at {T})::text t FROM mi_audit_log
                                 WHERE event_type='dead_column_detected' ORDER BY created_at""")
        print(f"{len(rows)} flagged columns, ever")
        for r in rows:
            key = r["summary"]
            if "." not in key:
                print("  ?", key); continue
            tbl, col = key.split(".", 1)
            try:
                n = await c.fetchval(f'SELECT count(*) FROM "{tbl}"')
                nn = await c.fetchval(f'SELECT count("{col}") FROM "{tbl}"')
                ts = await c.fetchval("""SELECT column_name FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=$1
                    AND column_name = ANY(ARRAY['updated_at','created_at','computed_at','recorded_at'])
                    ORDER BY array_position(ARRAY['updated_at','created_at','computed_at','recorded_at'], column_name::text) LIMIT 1""", tbl)
                first = None
                if nn and ts:
                    first = await c.fetchval(f'SELECT (min("{ts}") {T})::text FROM "{tbl}" WHERE "{col}" IS NOT NULL')
                print(f"  flagged {r['t'][:16]}  {key}  rows={n} populated={nn}  first_populated({ts})={first}")
            except Exception as e:
                print(f"  {key}: {type(e).__name__}: {str(e)[:100]}")


asyncio.run(main())
