"""2026-10-05 read-only: the two evening alerts — (1) cooldowns_per_day 29 vs median 2, (2) the dead
orderliness column on mi_anticipation_consolidation."""
import asyncio, json
from agents.market_intelligence.db import get_pool

D = "(created_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("now ET:", await c.fetchval("SELECT (now() AT TIME ZONE 'America/New_York')::text"))
        print("== 1. cooldowns written today, by reason (first 60 chars)")
        for r in await c.fetch("""SELECT LEFT(removal_reason,60) why, count(*) n, min(removed_at AT TIME ZONE 'America/New_York')::time t0,
                                  max(removed_at AT TIME ZONE 'America/New_York')::time t1
                                  FROM mi_validation_cooldowns WHERE (removed_at AT TIME ZONE 'America/New_York')::date
                                  = (now() AT TIME ZONE 'America/New_York')::date GROUP BY 1 ORDER BY 2 DESC"""):
            print(f"  {r['n']:3d}  {r['t0']}-{r['t1']}  {r['why']}")
        print("== 1b. cooldowns per day, last 10 days")
        for r in await c.fetch("""SELECT (removed_at AT TIME ZONE 'America/New_York')::date d, count(*) n FROM mi_validation_cooldowns
                                  WHERE removed_at > now() - interval '10 days' GROUP BY 1 ORDER BY 1"""):
            print(f"  {r['d']} {r['n']}")
        print("== 2. theme_retired_small_fading today")
        for r in await c.fetch(f"SELECT summary, detail FROM mi_audit_log WHERE event_type='theme_retired_small_fading' AND {D} ORDER BY created_at"):
            d = r["detail"] or ""
            print("  ", (r["summary"] or "")[:150], "|", d[:220])
        print("== 3. theme_rehome_judged today (summaries)")
        for r in await c.fetch(f"SELECT summary FROM mi_audit_log WHERE event_type='theme_rehome_judged' AND {D} ORDER BY created_at"):
            print("  ", (r["summary"] or "")[:200])
        for ev in ("theme_rehome_pass_ran", "theme_correctness_check"):
            for r in await c.fetch(f"SELECT summary, LEFT(detail, 600) det FROM mi_audit_log WHERE event_type=$1 AND {D}", ev):
                print(f"== {ev}:", (r["summary"] or "")[:300]); print("   ", r["det"])
        print("== 4. ep_adv_probe_synthesized per day, last 30 days")
        for r in await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n FROM mi_audit_log
                                  WHERE event_type='ep_adv_probe_synthesized' AND created_at > now() - interval '45 days'
                                  GROUP BY 1 ORDER BY 1"""):
            print(f"  {r['d']} {r['n']}")
        print("== 5. orderliness on mi_anticipation_consolidation")
        r = await c.fetchrow("""SELECT count(*) n, count(orderliness) n_ord, max(updated_at AT TIME ZONE 'America/New_York')::text last_upd,
                                count(*) FILTER (WHERE updated_at > now() - interval '1 day') n_upd_24h
                                FROM mi_anticipation_consolidation""")
        print("  ", dict(r))
        for r in await c.fetch(f"""SELECT event_type, summary, created_at AT TIME ZONE 'America/New_York' t FROM mi_audit_log
                                   WHERE event_type ILIKE '%consolidation_readiness%' AND created_at > now() - interval '4 days'
                                   ORDER BY created_at DESC LIMIT 4"""):
            print("  ", r["t"], r["event_type"], (r["summary"] or "")[:160])


asyncio.run(main())
