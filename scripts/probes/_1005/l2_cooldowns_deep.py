"""2026-10-05 read-only, part 2: (A) did tonight's 17:35 consolidation scan write `orderliness`
(the dead-column sweep ran 17:30, five minutes before the first post-deploy scan)?
(B) cooldowns_per_day 29: tonight's removal list, the true per-night history (audit rows, since
mi_validation_cooldowns upserts on (ticker, theme) and so re-dates re-removals), and the baseline
the L2 used. NO writes."""
import asyncio, json
from agents.market_intelligence.db import get_pool

ET = "AT TIME ZONE 'America/New_York'"
TODAY = f"(created_at {ET})::date = (now() {ET})::date"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("now ET:", await c.fetchval(f"SELECT (now() {ET})::text"))

        print("\n== A1. orderliness now")
        r = await c.fetchrow(f"""SELECT count(*) n, count(orderliness) n_ord,
              count(*) FILTER (WHERE (updated_at {ET})::date = (now() {ET})::date) n_upd_today,
              count(orderliness) FILTER (WHERE (updated_at {ET})::date = (now() {ET})::date) n_ord_today,
              max(updated_at {ET})::text last_upd,
              min(orderliness) mn, percentile_cont(0.5) WITHIN GROUP (ORDER BY orderliness) med, max(orderliness) mx
              FROM mi_anticipation_consolidation""")
        print("  ", dict(r))
        for r in await c.fetch(f"""SELECT ticker, state, orderliness, (updated_at {ET})::text u FROM mi_anticipation_consolidation
                                   WHERE (updated_at {ET})::date = (now() {ET})::date ORDER BY updated_at DESC LIMIT 8"""):
            print("   ", dict(r))
        print("== A2. dead_column_detected rows (all time)")
        for r in await c.fetch(f"""SELECT (created_at {ET})::text t, summary FROM mi_audit_log
                                   WHERE event_type='dead_column_detected' ORDER BY created_at"""):
            print("  ", r["t"], r["summary"])
        print("== A3. consolidation-related audit events today")
        for r in await c.fetch(f"""SELECT (created_at {ET})::time t, event_type, LEFT(summary,140) s FROM mi_audit_log
                                   WHERE {TODAY} AND (event_type ILIKE '%consolidation%' OR summary ILIKE '%consolidation_readiness%')
                                   ORDER BY created_at LIMIT 15"""):
            print("  ", r["t"], r["event_type"], r["s"])

        print("\n== B1. tonight's cooldown rows (ticker | theme | reason)")
        for r in await c.fetch(f"""SELECT ticker, theme_name, removal_reason, removal_count FROM mi_validation_cooldowns
                                   WHERE (removed_at {ET})::date = (now() {ET})::date ORDER BY theme_name, ticker"""):
            print(f"  {r['ticker']:6s} | {r['theme_name'][:70]:70s} | n={r['removal_count']} | {(r['removal_reason'] or '')[:150]}")

        print("\n== B2. tonight's description removals: theme first-seen date + member count tonight")
        for r in await c.fetch(f"""
            WITH tonight AS (SELECT DISTINCT theme_name FROM mi_validation_cooldowns
                             WHERE (removed_at {ET})::date = (now() {ET})::date AND removal_reason LIKE 'Description%%')
            SELECT t.theme_name,
                   (SELECT min(theme_date) FROM mi_themes m WHERE m.name = t.theme_name) first_seen,
                   (SELECT stage FROM mi_themes m WHERE m.name = t.theme_name ORDER BY theme_date DESC LIMIT 1) stage,
                   (SELECT cardinality(tickers) FROM mi_themes m WHERE m.name = t.theme_name ORDER BY theme_date DESC LIMIT 1) n_now,
                   (SELECT max(theme_date) FROM mi_themes m WHERE m.name = t.theme_name) last_seen
            FROM tonight t ORDER BY 2"""):
            print("  ", dict(r))

        print("\n== B3. TRUE per-night history (audit rows, not the upserted table), last 45 days")
        rows = await c.fetch(f"""
            SELECT (created_at {ET})::date d, extract(isodow from (created_at {ET})::date)::int dow,
                   count(*) FILTER (WHERE event_type='ticker_revalidated_out') desc_out,
                   count(*) FILTER (WHERE event_type='validation_cooldown_triggered') cd_trig
            FROM mi_audit_log WHERE created_at > now() - interval '45 days'
              AND event_type IN ('ticker_revalidated_out','validation_cooldown_triggered')
            GROUP BY 1,2 ORDER BY 1""")
        samples = {}
        for r in await c.fetch("""SELECT detail FROM mi_audit_log WHERE event_type='metric_sample' AND summary='cooldowns_per_day'
                                  AND created_at > now() - interval '45 days' ORDER BY created_at"""):
            p = json.loads(r["detail"] or "{}")
            samples[p.get("as_of")] = p.get("value")
        byd = {str(r["d"]): r for r in rows}
        alld = sorted(set(byd) | set(samples))
        print("  date        dow  desc_removals(audit)  cooldown_triggered(audit)  metric_sample(what L2 saw)")
        for d in alld:
            r = byd.get(d)
            from datetime import date as _d
            dow = _d.fromisoformat(d).isoweekday()
            print(f"  {d}  {dow}    {r['desc_out'] if r else 0:5d}                {r['cd_trig'] if r else 0:5d}                  {samples.get(d)}")

        print("\n== B4. themes on the board each validation night (mi_themes rows, members>=2), last 30 days")
        for r in await c.fetch("""SELECT theme_date d, count(*) themes, count(*) FILTER (WHERE cardinality(tickers)>=2) themes2,
                                  sum(cardinality(tickers)) members
                                  FROM mi_themes WHERE theme_date > current_date - 30 AND extract(isodow from theme_date) IN (1,3,5)
                                  AND coalesce(stage,'') <> 'Retired'
                                  GROUP BY 1 ORDER BY 1"""):
            print("  ", dict(r))

        print("\n== B5. baseline the L2 used + tonight's anomaly row")
        for r in await c.fetch("""SELECT as_of_date, p50, p95, mad, sample_n FROM mi_metric_baselines
                                  WHERE metric_name='cooldowns_per_day' ORDER BY as_of_date DESC LIMIT 6"""):
            print("  ", dict(r))
        for r in await c.fetch(f"""SELECT (created_at {ET})::text t, LEFT(detail, 600) d FROM mi_audit_log
                                   WHERE event_type='anomaly_detected' AND detail LIKE '%cooldowns_per_day%'
                                   AND created_at > now() - interval '40 days' ORDER BY created_at"""):
            print("  ", r["t"], r["d"])
        print("== B6. baseline resets for cooldowns_per_day")
        for r in await c.fetch("SELECT reset_at, reason FROM mi_baseline_resets WHERE metric_name='cooldowns_per_day' ORDER BY reset_at"):
            print("  ", dict(r))


asyncio.run(main())
