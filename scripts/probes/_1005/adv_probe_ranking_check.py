"""2026-10-05 read-only follow-up: is the EP shortlist's liquidity axis EVER live (adv_source at sort
time), and what decides the rank-20 cut on a >20-candidate morning (today)."""
import asyncio
from agents.market_intelligence.db import get_pool

ET = "AT TIME ZONE 'America/New_York'"
TODAY = f"(now() {ET})::date"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("now ET:", await c.fetchval(f"SELECT (now() {ET})::text"))
        print("== C1. mi_ep_scan_log adv_source by month (has 'rs_universe' EVER appeared?)")
        for r in await c.fetch("""SELECT date_trunc('month', scan_date)::date m, count(*) n,
                   count(*) FILTER (WHERE adv_source='rs_universe') rsu, count(*) FILTER (WHERE adv_source='polygon_20d') poly,
                   count(*) FILTER (WHERE adv_source='pending') pend, count(*) FILTER (WHERE adv_source IS NULL) nul,
                   max(scan_date) FILTER (WHERE adv_source='rs_universe') last_rsu
                   FROM mi_ep_scan_log GROUP BY 1 ORDER BY 1"""):
            print("  ", dict(r))
        print("== C2. mi_ep_shortlist_shadow whole history: adv_source + days whose board exceeded 20")
        print("  ", dict(await c.fetchrow("""SELECT min(scan_date) d0, max(scan_date) d1, count(*) n,
                   count(*) FILTER (WHERE adv_source IN ('rs_universe','polygon_20d')) real_adv,
                   count(DISTINCT scan_date) days FROM mi_ep_shortlist_shadow""")))
        for r in await c.fetch("""SELECT scan_date, max(board_n) mb, count(DISTINCT scan_time_et) FILTER (WHERE board_n > 20) ticks_over_20
                   FROM mi_ep_shortlist_shadow GROUP BY 1 HAVING max(board_n) > 20 ORDER BY 1"""):
            print("   board>20:", dict(r))
        print("== C3. mi_stock_scores: when are a score_date's rows written? (columns)")
        cols = [r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mi_stock_scores' ORDER BY ordinal_position")]
        print("  ", cols)
        for cand in ("created_at", "updated_at", "computed_at"):
            if cand in cols:
                for r in await c.fetch(f"""SELECT score_date, min({cand} {ET})::text t0, max({cand} {ET})::text t1
                        FROM mi_stock_scores WHERE score_date > current_date - 5 GROUP BY 1 ORDER BY 1"""):
                    print(f"   {cand}:", dict(r))
        print("  rs job audit rows last 3 days:")
        for r in await c.fetch(f"""SELECT (created_at {ET})::text t, event_type, LEFT(summary,120) s FROM mi_audit_log
                   WHERE created_at > now() - interval '3 days' AND (event_type ILIKE '%rs_%' OR event_type ILIKE '%nightly%')
                   ORDER BY created_at DESC LIMIT 8"""):
            print("    ", dict(r))
        print("== C4. how many of today's gap names WERE in yesterday's (10-02) RS universe with an ADV?")
        r = await c.fetchrow(f"""SELECT count(DISTINCT s.ticker) n,
                   count(DISTINCT s.ticker) FILTER (WHERE m.adv_20 IS NOT NULL) in_rsu_prevday
                   FROM mi_ep_shortlist_shadow s LEFT JOIN mi_stock_scores m
                     ON m.ticker = s.ticker AND m.score_date = (SELECT max(score_date) FROM mi_stock_scores WHERE score_date < {TODAY})
                   WHERE s.scan_date = {TODAY}""")
        print("  ", dict(r))
        print("== C5. the 09:20 tick's shortlist order (rank_by_prescore, theme flag, ticker) — what decided the cut")
        for r in await c.fetch(f"""SELECT rank_by_prescore rp, rank_by_gap rg, ticker, in_active_theme th, adv_source src,
                   round(gap_pct::numeric,1) gap, shortlisted_by_prescore sl
                   FROM mi_ep_shortlist_shadow WHERE scan_date={TODAY}
                   AND scan_time_et = (SELECT min(scan_time_et) FROM mi_ep_shortlist_shadow WHERE scan_date={TODAY}
                                       AND (scan_time_et {ET})::time >= '09:20')
                   ORDER BY rank_by_prescore"""):
            print("  ", dict(r))
        print("== C6. names today that were cut at the rank-20 line on some tick and NEVER graded all day")
        for r in await c.fetch(f"""
            WITH cut AS (SELECT DISTINCT ticker FROM mi_ep_shortlist_shadow WHERE scan_date={TODAY} AND NOT shortlisted_by_prescore),
                 graded AS (SELECT DISTINCT ticker FROM mi_ep_scan_log WHERE scan_date={TODAY} AND ep_score IS NOT NULL)
            SELECT l.ticker, count(*) rows, max(l.gap_pct) max_gap, max(l.rel_volume) max_rv, max(l.projected_vol_multiple) max_proj,
                   min(l.rank_by_gap) best_gap_rank, string_agg(DISTINCT LEFT(l.filter_reason,60), ' | ') reasons
            FROM mi_ep_scan_log l WHERE l.scan_date={TODAY} AND l.ticker IN (SELECT ticker FROM cut)
              AND l.ticker NOT IN (SELECT ticker FROM graded)
            GROUP BY 1 ORDER BY max_gap DESC"""):
            print("  ", dict(r))
        print("== C7. SDEV today, every scan-log row")
        for r in await c.fetch(f"""SELECT (scan_time_et {ET})::time::text t, gap_pct, rel_volume, rank_by_gap, adv_source,
                   LEFT(filter_reason,110) why, ep_score FROM mi_ep_scan_log WHERE scan_date={TODAY} AND ticker='SDEV'
                   ORDER BY scan_time_et"""):
            print("  ", dict(r))


asyncio.run(main())
