"""2026-10-05 read-only: did tonight's 17:35 consolidation_readiness run (the first since the #394
orderliness column shipped) write orderliness, and when did the 17:30 dead-column sweep fire?"""
import asyncio
from agents.market_intelligence.db import get_pool

T = "AT TIME ZONE 'America/New_York'"
TODAY = f"(created_at {T})::date = (now() {T})::date"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("now ET:", await c.fetchval(f"SELECT (now() {T})::text"))
        print("== mi_job_runs today: post_nightly_audit / consolidation_readiness")
        for r in await c.fetch(f"""SELECT job_id, status, (started_at {T})::time s, (finished_at {T})::time f
                                   FROM mi_job_runs WHERE job_id IN ('post_nightly_audit','consolidation_readiness')
                                   AND started_at > now() - interval '4 days' ORDER BY started_at""") if True else []:
            print("  ", dict(r))
        print("== dead_column_detected audit rows (all time)")
        for r in await c.fetch(f"""SELECT (created_at {T})::text t, summary, detail FROM mi_audit_log
                                   WHERE event_type='dead_column_detected' ORDER BY created_at DESC LIMIT 12"""):
            print("  ", r["t"], r["summary"], r["detail"])
        print("== mi_anticipation_consolidation orderliness")
        r = await c.fetchrow(f"""SELECT count(*) n, count(orderliness) n_ord,
                 max(updated_at {T})::text last_upd,
                 count(*) FILTER (WHERE (updated_at {T})::date = (now() {T})::date) n_today,
                 count(orderliness) FILTER (WHERE (updated_at {T})::date = (now() {T})::date) n_today_ord,
                 count(*) FILTER (WHERE last_eval = (now() {T})::date) n_eval_today,
                 count(*) FILTER (WHERE state <> 'aged') n_nonaged
                 FROM mi_anticipation_consolidation""")
        print("  ", dict(r))
        print("== today's rows by state (n, n with orderliness)")
        for r in await c.fetch(f"""SELECT state, count(*) n, count(orderliness) n_ord,
                 round(min(orderliness)::numeric,2) mn, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY orderliness)::numeric,2) med,
                 round(max(orderliness)::numeric,2) mx
                 FROM mi_anticipation_consolidation WHERE (updated_at {T})::date = (now() {T})::date GROUP BY 1"""):
            print("  ", dict(r))
        print("== last_eval distribution (how many rows the nightly rewrite never touches again)")
        for r in await c.fetch("""SELECT last_eval, count(*) n FROM mi_anticipation_consolidation
                                  GROUP BY 1 ORDER BY 1 DESC LIMIT 8"""):
            print("  ", r["last_eval"], r["n"])
        print("== consolidation audit events today")
        for r in await c.fetch(f"""SELECT event_type, count(*) n, min(created_at {T})::time t0, max(created_at {T})::time t1
                                   FROM mi_audit_log WHERE {TODAY} AND (event_type ILIKE '%consolidation%'
                                   OR event_type ILIKE '%anticipation%' OR event_type ILIKE 'mna_filter%')
                                   GROUP BY 1 ORDER BY 3"""):
            print("  ", dict(r))


asyncio.run(main())
