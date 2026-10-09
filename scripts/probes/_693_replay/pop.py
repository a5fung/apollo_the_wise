"""#693 replay — population probe (read-only)."""
import asyncio, json
from agents.market_intelligence.db import get_pool
ET = "AT TIME ZONE 'America/New_York'"
async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        cols = [r['column_name'] for r in await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='api_usage'")]
        print("api_usage cols", cols)
        tcol = 'created_at' if 'created_at' in cols else ('ts' if 'ts' in cols else cols[-1])
        print("\n== theme_validation calls by ET day (since 09-25)")
        for r in await c.fetch(f"""SELECT ({tcol} {ET})::date d, model, count(*) n, sum(input_tokens) i, sum(output_tokens) o,
              round(avg(output_tokens)) ao, round(avg(input_tokens)) ai, sum(cost_usd) cost,
              string_agg(DISTINCT coalesce(stop_reason,'NULL'), ',') sr,
              min(({tcol} {ET})::time)::text t0, max(({tcol} {ET})::time)::text t1
            FROM api_usage WHERE caller='theme_validation' AND {tcol} > '2026-09-25' GROUP BY 1,2 ORDER BY 1"""):
            print("  ", dict(r))
        print("\n== audit events on 10-05 ET related to validation")
        for r in await c.fetch(f"""SELECT event_type, count(*) n FROM mi_audit_log
             WHERE (created_at {ET})::date='2026-10-05' AND (event_type LIKE '%valid%' OR event_type LIKE '%dissol%' OR event_type LIKE '%mass%' OR event_type LIKE '%rewrite%')
             GROUP BY 1 ORDER BY 1"""):
            print("  ", dict(r))
        print("\n== ticker_revalidated_out 10-05")
        for r in await c.fetch(f"""SELECT (created_at {ET})::time::text t, summary, detail FROM mi_audit_log
             WHERE (created_at {ET})::date='2026-10-05' AND event_type='ticker_revalidated_out' ORDER BY created_at"""):
            print("  ", r['t'][:8], r['summary'], '||', (r['detail'] or '')[:140])
        print("\n== validation_removal_shielded / mass / error 10-05")
        for r in await c.fetch(f"""SELECT event_type, (created_at {ET})::time::text t, summary, left(detail,200) d FROM mi_audit_log
             WHERE (created_at {ET})::date='2026-10-05' AND event_type IN ('validation_removal_shielded','validation_mass_removal_name_suspect','validation_error','validation_api_failure','validation_rate_limited')
             ORDER BY created_at"""):
            print("  ", dict(r))
        print("\n== cooldowns 10-05")
        rows = await c.fetch(f"""SELECT ticker, theme_name, (removed_at {ET})::time::text t, removal_reason FROM mi_validation_cooldowns
              WHERE (removed_at {ET})::date='2026-10-05' ORDER BY removed_at""")
        print("  n=", len(rows), " description-reason n=", sum(1 for r in rows if (r['removal_reason'] or '').startswith('Description')))
asyncio.run(main())
