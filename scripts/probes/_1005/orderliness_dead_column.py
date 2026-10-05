"""2026-10-05 read-only: is mi_anticipation_consolidation.orderliness really dead, or flagged by the
17:30 dead-column sweep five minutes before the 17:35 scan (its only writer) first ran with it?"""
import asyncio, inspect
from agents.market_intelligence.db import get_pool
import agents.market_intelligence.db as dbm


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("now ET:", await c.fetchval("SELECT (now() AT TIME ZONE 'America/New_York')::text"))
        print("== running code: upsert_consolidation writes orderliness?",
              "orderliness" in inspect.getsource(dbm.upsert_consolidation))
        r = await c.fetchrow("""SELECT count(*) n, count(orderliness) n_ord,
                 max(updated_at AT TIME ZONE 'America/New_York')::text last_upd,
                 count(*) FILTER (WHERE (updated_at AT TIME ZONE 'America/New_York')::date
                                  = (now() AT TIME ZONE 'America/New_York')::date) n_upd_today,
                 count(orderliness) FILTER (WHERE (updated_at AT TIME ZONE 'America/New_York')::date
                                  = (now() AT TIME ZONE 'America/New_York')::date) n_ord_today,
                 count(*) FILTER (WHERE last_eval = (now() AT TIME ZONE 'America/New_York')::date) n_eval_today
                 FROM mi_anticipation_consolidation""")
        print("== table:", dict(r))
        print("== rows written per updated_at day (last 8 days)")
        for x in await c.fetch("""SELECT (updated_at AT TIME ZONE 'America/New_York')::date d, count(*) n,
                 count(orderliness) n_ord, min(orderliness) mn, max(orderliness) mx
                 FROM mi_anticipation_consolidation WHERE updated_at > now() - interval '8 days' GROUP BY 1 ORDER BY 1"""):
            print("  ", dict(x))
        print("== today's scored sample")
        for x in await c.fetch("""SELECT ticker, state, orderliness, updated_at AT TIME ZONE 'America/New_York' t
                 FROM mi_anticipation_consolidation WHERE orderliness IS NOT NULL ORDER BY updated_at DESC LIMIT 8"""):
            print("  ", dict(x))
        print("== job audit rows today (dead-column sweep / scan / post-nightly)")
        for x in await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary,200) s
                 FROM mi_audit_log WHERE created_at > now() - interval '20 hours'
                   AND (event_type ILIKE '%dead_column%' OR event_type ILIKE '%consolidation%'
                        OR summary ILIKE '%consolidation_readiness%' OR summary ILIKE '%post_nightly_audit%'
                        OR event_type ILIKE '%coil%')
                 ORDER BY created_at LIMIT 40"""):
            print("  ", x["t"], x["event_type"], "|", x["s"])
        print("== all dead_column_detected ever")
        for x in await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, summary FROM mi_audit_log
                 WHERE event_type='dead_column_detected' ORDER BY created_at"""):
            print("  ", x["t"], x["summary"])
        print("== column add time proxy: pg_attribute exists?",
              await c.fetchval("""SELECT count(*) FROM information_schema.columns
                 WHERE table_name='mi_anticipation_consolidation' AND column_name='orderliness'"""))

asyncio.run(main())
