"""2026-10-05 read-only: (A) why ep_adv_probe_synthesized went ~0 -> 94 today; (B) whether tonight's
17:35 consolidation scan wrote mi_anticipation_consolidation.orderliness (dead-column alert fired 17:30)."""
import asyncio, json
from collections import Counter, defaultdict
from agents.market_intelligence.db import get_pool

ET = "AT TIME ZONE 'America/New_York'"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("now ET:", await c.fetchval(f"SELECT (now() {ET})::text"))

        print("== A1. mi_stock_scores rows per score_date (last 14 days) — the adv_map source")
        for r in await c.fetch("""SELECT score_date, count(*) n, count(adv_20) n_adv FROM mi_stock_scores
                                  WHERE score_date > current_date - 14 GROUP BY 1 ORDER BY 1"""):
            print(f"  {r['score_date']} rows={r['n']} adv20={r['n_adv']}")
        print("  latest score_date row created? ",
              await c.fetchval("SELECT max(score_date)::text FROM mi_stock_scores"))

        print("== A2. ep_adv_probe_synthesized — all rows on 09-17 and today, grouped by minute")
        rows = await c.fetch(f"""SELECT (created_at {ET}) t, summary, detail FROM mi_audit_log
                                 WHERE event_type='ep_adv_probe_synthesized' AND created_at > now() - interval '60 days'
                                 ORDER BY created_at""")
        byday = defaultdict(list)
        for r in rows:
            byday[r["t"].date()].append(r)
        for d, rs in byday.items():
            mins = Counter(r["t"].strftime("%H:%M") for r in rs)
            tick = Counter(json.loads(r["detail"])["ticker"] for r in rs)
            print(f"  {d}: {len(rs)} rows, {len(tick)} distinct tickers, minutes={dict(sorted(mins.items()))}")
            for r in rs[:200]:
                dd = json.loads(r["detail"])
                print(f"    {r['t'].strftime('%H:%M:%S')} {dd['ticker']:6s} rg={dd.get('rank_by_gap')} rp={dd.get('rank_by_prescore')} "
                      f"gap={dd.get('gap_pct')} rv={dd.get('rel_volume')} adv={dd.get('adv_polygon_20d')} vol={dd.get('today_volume')}")

        print("== A3. mi_ep_shortlist_shadow per scan_date (last 15 days)")
        for r in await c.fetch(f"""
            SELECT scan_date, count(*) n, count(DISTINCT scan_time_et) ticks, max(board_n) max_board,
                   string_agg(DISTINCT acting_key, ',') acting,
                   count(*) FILTER (WHERE adv_source='pending') n_pending,
                   count(*) FILTER (WHERE adv_source='rs_universe') n_rsu,
                   count(*) FILTER (WHERE adv_source='polygon_20d') n_poly,
                   count(*) FILTER (WHERE adv_source='pending' AND rank_by_prescore BETWEEN 21 AND 50) n_pend_21_50,
                   count(*) FILTER (WHERE adv_source='pending' AND rank_by_prescore <= 20) n_pend_top20,
                   count(DISTINCT ticker) FILTER (WHERE shortlisted_by_prescore) n_shortlisted_names,
                   min((scan_time_et {ET})::time)::text t0, max((scan_time_et {ET})::time)::text t1
            FROM mi_ep_shortlist_shadow WHERE scan_date > current_date - 15 GROUP BY 1 ORDER BY 1"""):
            print("  ", dict(r))

        print("== A3b. today's shortlist shadow per tick")
        for r in await c.fetch(f"""
            SELECT (scan_time_et {ET})::time::text t, minutes_since_open m, count(*) n, max(board_n) b, max(acting_key) ak,
                   count(*) FILTER (WHERE adv_source='pending') pend,
                   count(*) FILTER (WHERE adv_source='pending' AND rank_by_prescore BETWEEN 21 AND 50) pend_21_50,
                   count(*) FILTER (WHERE adv_source='pending' AND rank_by_prescore <= 20) pend_top20
            FROM mi_ep_shortlist_shadow WHERE scan_date = (now() {ET})::date GROUP BY 1,2 ORDER BY 1"""):
            print("  ", dict(r))

        print("== A3c. last 5 market days' shortlist shadow per tick (pending in 21-50)")
        for r in await c.fetch(f"""
            SELECT scan_date, (scan_time_et {ET})::time::text t, count(*) n, max(board_n) b,
                   count(*) FILTER (WHERE adv_source='pending') pend,
                   count(*) FILTER (WHERE adv_source='pending' AND rank_by_prescore BETWEEN 21 AND 50) pend_21_50
            FROM mi_ep_shortlist_shadow WHERE scan_date > current_date - 8 AND scan_date < (now() {ET})::date
            GROUP BY 1,2 ORDER BY 1,2"""):
            print("  ", dict(r))

        print("== A4. mi_ep_scan_log per scan_date (last 15 days)")
        for r in await c.fetch(f"""
            SELECT scan_date, count(*) n, count(DISTINCT ticker) names, count(DISTINCT scan_time_et) ticks,
                   count(DISTINCT ticker) FILTER (WHERE ep_score IS NOT NULL) graded_names,
                   count(*) FILTER (WHERE ep_score IS NOT NULL) graded_rows,
                   count(DISTINCT ticker) FILTER (WHERE score_tier='HIGH') high_names,
                   count(*) FILTER (WHERE adv_source='pending') pend, count(*) FILTER (WHERE adv_source='polygon_20d') poly,
                   count(*) FILTER (WHERE adv_source='rs_universe') rsu
            FROM mi_ep_scan_log WHERE scan_date > current_date - 15 GROUP BY 1 ORDER BY 1"""):
            print("  ", dict(r))

        print("== A5. today's graded names (ep_score not null) and their adv_source")
        for r in await c.fetch(f"""
            SELECT ticker, max(ep_score) s, max(score_tier) tier, string_agg(DISTINCT adv_source, ',') src,
                   min(rank_by_gap) rg, min((scan_time_et {ET})::time)::text t
            FROM mi_ep_scan_log WHERE scan_date=(now() {ET})::date AND ep_score IS NOT NULL
            GROUP BY 1 ORDER BY s DESC NULLS LAST"""):
            print("  ", dict(r))

        print("== A6. ep scan job audit rows today")
        for r in await c.fetch(f"""SELECT event_type, count(*) n, min((created_at {ET})::time)::text t0, max((created_at {ET})::time)::text t1
                                  FROM mi_audit_log WHERE (created_at {ET})::date=(now() {ET})::date
                                  AND (event_type ILIKE 'ep_scan%' OR event_type ILIKE '%adv%' OR event_type ILIKE 'job_%ep%')
                                  GROUP BY 1 ORDER BY 2 DESC LIMIT 30"""):
            print("  ", dict(r))

        print("== B1. orderliness now")
        r = await c.fetchrow(f"""SELECT count(*) n, count(orderliness) n_ord,
                                count(*) FILTER (WHERE last_eval=(now() {ET})::date) n_eval_today,
                                count(orderliness) FILTER (WHERE last_eval=(now() {ET})::date) n_ord_today,
                                max(updated_at {ET})::text last_upd,
                                min(orderliness) mn, max(orderliness) mx,
                                count(*) FILTER (WHERE state <> 'aged') n_live
                                FROM mi_anticipation_consolidation""")
        print("  ", dict(r))
        for r in await c.fetch(f"""SELECT state, count(*) n, count(orderliness) n_ord,
                                count(*) FILTER (WHERE last_eval=(now() {ET})::date) eval_today
                                FROM mi_anticipation_consolidation GROUP BY 1 ORDER BY 2 DESC"""):
            print("    ", dict(r))
        print("== B2. consolidation_readiness + dead_column audit rows (last 4 days)")
        for r in await c.fetch(f"""SELECT (created_at {ET})::text t, event_type, LEFT(summary,200) s FROM mi_audit_log
                                   WHERE (event_type ILIKE '%consolidation_readiness%' OR event_type='dead_column_detected'
                                          OR event_type ILIKE 'job_%consolidation%')
                                   AND created_at > now() - interval '4 days' ORDER BY created_at DESC LIMIT 12"""):
            print("  ", dict(r))
        print("== B3. the first upsert of the column — when did the ALTER land (market-agent boot)?")
        for r in await c.fetch(f"""SELECT (created_at {ET})::text t, event_type, LEFT(summary,140) s FROM mi_audit_log
                                   WHERE event_type ILIKE '%boot%' AND created_at > now() - interval '4 days'
                                   ORDER BY created_at DESC LIMIT 6"""):
            print("  ", dict(r))


asyncio.run(main())
