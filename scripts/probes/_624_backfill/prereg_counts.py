"""#624 backfill — PRE-REGISTRATION sizing read (2026-10-06). READ-ONLY, INPUTS ONLY.

Reads NO outcome table (mi_lowcap_lane_replays is never touched). Purpose: the counts the
pre-registration's pull plan needs, and the input columns of the live lane rows + the
mi_universe_floor_shadow coverage that the volume-proxy calibration will use.
Run inside apollo-market:  docker exec -w /app apollo-market python /tmp/x.py
"""
import asyncio

from agents.market_intelligence.db import get_pool

W0, W1 = "2024-01-02", "2026-09-03"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("=== mi_splits coverage")
        print(dict(await c.fetchrow(
            "SELECT count(*) n, min(execution_date) lo, max(execution_date) hi, "
            "count(*) FILTER (WHERE adjustment_applied) applied FROM mi_splits")))
        print("=== mi_security_types")
        for r in await c.fetch("SELECT security_type, count(*) n FROM mi_security_types GROUP BY 1 ORDER BY 2 DESC"):
            print(dict(r))

        print("=== daily prefilter counts (adjusted values; raw un-adjust via mi_splits)")
        rows = await c.fetch(f"""
            WITH x AS (
              SELECT ticker, trade_date, open_price o, high_price h, close cl, volume v,
                     lag(close)  OVER w pc, lag(volume) OVER w pv
              FROM mi_daily_closes WHERE trade_date >= '2023-12-01'
              WINDOW w AS (PARTITION BY ticker ORDER BY trade_date)),
            f AS (
              SELECT x.*, COALESCE((SELECT exp(sum(ln(s.split_to::float / s.split_from)))
                                    FROM mi_splits s WHERE s.ticker = x.ticker
                                      AND s.execution_date > x.trade_date - 1), 1.0) fac
              FROM x
              WHERE x.trade_date BETWEEN '{W0}' AND '{W1}' AND x.pc > 0
                AND (x.h >= x.pc * 1.15 OR x.o >= x.pc * 1.10))
            SELECT extract(year FROM trade_date)::int yr,
              count(*) FILTER (WHERE o >= pc*1.15 AND pc >= 5)                         a_open15_adj5,
              count(*) FILTER (WHERE o >= pc*1.15 AND pc*fac >= 5)                     b_open15_raw5,
              count(*) FILTER (WHERE h >= pc*1.15 AND pc*fac >= 5)                     c_high15_raw5,
              count(*) FILTER (WHERE h >= pc*1.15 AND o >= pc*1.05 AND pc*fac >= 5)    d_high15_open5_raw5,
              count(*) FILTER (WHERE h >= pc*1.15 AND o >= pc*1.10 AND pc*fac >= 5)    e_high15_open10_raw5,
              count(*) FILTER (WHERE h >= pc*1.15 AND pc*fac >= 5 AND pv/fac >= 50000) f_c_plus_pv50k,
              count(*) FILTER (WHERE h >= pc*1.15 AND pc*fac >= 5 AND pv/fac >= 50000
                               AND ticker ~ '^[A-Z]{{1,5}}$')                           g_f_plus_symbol,
              count(*) FILTER (WHERE h >= pc*1.15 AND pc*fac >= 5 AND pv/fac >= 50000
                               AND ticker ~ '^[A-Z]{{1,5}}$'
                               AND ticker IN (SELECT ticker FROM mi_security_types WHERE security_type IN ('CS','ADRC'))) h_g_typed_stock,
              count(*) FILTER (WHERE h >= pc*1.15 AND pc*fac >= 5 AND pv/fac >= 50000
                               AND ticker ~ '^[A-Z]{{1,5}}$'
                               AND ticker NOT IN (SELECT ticker FROM mi_security_types)) i_g_untyped,
              count(DISTINCT ticker) FILTER (WHERE h >= pc*1.15 AND pc*fac >= 5 AND pv/fac >= 50000
                               AND ticker ~ '^[A-Z]{{1,5}}$')                           j_g_names,
              count(*) FILTER (WHERE fac <> 1.0)                                         k_rows_with_later_split
            FROM f GROUP BY 1 ORDER BY 1""")
        for r in rows:
            print(dict(r))

        print("=== live lane rows: INPUT columns only (no outcome table read)")
        for r in await c.fetch("""
            SELECT ticker, scan_date, tick_wallclock_et AT TIME ZONE 'America/New_York' tick_et,
                   minutes_since_open, round(gap_pct::numeric,1) gap, round(gap_pct_rt::numeric,1) gap_rt,
                   round(gap_pct_delayed::numeric,1) gap_dl, price_source, prev_close, current_price,
                   round((market_cap/1e6)::numeric,0) cap_m, today_volume_delayed vol_dl, today_volume_rt vol_rt,
                   rt_pm_bars, rt_session_bars, vol_percentile, vol_history_n, round(extension_pct::numeric,1) ext,
                   in_shortlist, jsonb_array_length(blocking_filters) n_block
            FROM mi_lowcap_lane_signals ORDER BY scan_date, ticker"""):
            print("|".join(str(v) for v in r.values()))

        print("=== mi_universe_floor_shadow: calibration-window coverage (2026-09-09..2026-10-05)")
        print(dict(await c.fetchrow("""
            SELECT count(*) n_all,
                   count(*) FILTER (WHERE today_volume_at_open IS NOT NULL) n_vol_at_open,
                   count(*) FILTER (WHERE today_volume_at_open IS NOT NULL AND gap_pct_at_open >= 15
                                    AND prev_close >= 5) n_gap15_px5,
                   count(DISTINCT scan_date) sessions,
                   min(minutes_since_open_at_open) msoo_min, max(minutes_since_open_at_open) msoo_max
            FROM mi_universe_floor_shadow WHERE scan_date BETWEEN '2026-09-09' AND '2026-10-05'""")))
        for r in await c.fetch("""
            SELECT minutes_since_open_at_open m, count(*) n FROM mi_universe_floor_shadow
            WHERE scan_date BETWEEN '2026-09-09' AND '2026-10-05' AND today_volume_at_open IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC LIMIT 8"""):
            print(dict(r))


asyncio.run(main())
