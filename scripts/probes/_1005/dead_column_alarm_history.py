"""2026-10-05 read-only: of every column the dead-column sweep ever announced, how many are populated
now and when was the first non-null write — i.e. how often the 17:30 sweep fires before the writer."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, summary FROM mi_audit_log
                                WHERE event_type='dead_column_detected' ORDER BY created_at""")
        for r in rows:
            table, col = r["summary"].split(".", 1)
            try:
                exists = await c.fetchval("""SELECT count(*) FROM information_schema.columns
                                             WHERE table_name=$1 AND column_name=$2""", table, col)
                if not exists:
                    print(f"{r['t']:%m-%d %H:%M}  {r['summary']:60s} DROPPED"); continue
                n_now = await c.fetchval(f'SELECT count("{col}") FROM "{table}"')
                tcols = {x["column_name"] for x in await c.fetch(
                    "SELECT column_name FROM information_schema.columns WHERE table_name=$1", table)}
                tscol = next((x for x in ("updated_at", "created_at", "computed_at", "logged_at") if x in tcols), None)
                first = None
                if n_now and tscol:
                    first = await c.fetchval(f'SELECT min("{tscol}") FROM "{table}" WHERE "{col}" IS NOT NULL')
                print(f"{r['t']:%m-%d %H:%M}  {r['summary']:60s} non-null now={n_now}  first_nonnull_{tscol}={first}")
            except Exception as e:
                print(f"{r['summary']} ERR {type(e).__name__}: {str(e)[:100]}")

asyncio.run(main())
