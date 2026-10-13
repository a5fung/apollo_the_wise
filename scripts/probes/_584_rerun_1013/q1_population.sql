\echo === Q1a: per scan_date
SELECT scan_date, count(*) rows, count(*) FILTER (WHERE failed_price_floor OR failed_volume_floor) rejected,
  count(*) FILTER (WHERE NOT (failed_price_floor OR failed_volume_floor)) admitted,
  count(*) FILTER (WHERE (failed_price_floor OR failed_volume_floor) AND today_dollar_volume_at_open IS NOT NULL) rej_atopen,
  count(*) FILTER (WHERE (failed_price_floor OR failed_volume_floor) AND today_dollar_volume_at_open IS NULL AND today_dollar_volume_last IS NOT NULL AND minutes_since_open_last<=15) rej_fallback_last15,
  max(last_seen_et AT TIME ZONE 'America/New_York') last_seen_et
FROM mi_universe_floor_shadow GROUP BY 1 ORDER BY 1;
\echo === Q1b: overall
SELECT count(*), count(DISTINCT scan_date) dates, min(scan_date), max(scan_date), count(DISTINCT ticker) names FROM mi_universe_floor_shadow;
\echo === Q1c: acting floors
SELECT acting_price_floor, acting_volume_floor, min(scan_date), max(scan_date), count(*) FROM mi_universe_floor_shadow GROUP BY 1,2;
\echo === Q1d: closes coverage
SELECT trade_date, count(*) n FROM mi_daily_closes WHERE trade_date >= DATE '2026-09-25' GROUP BY 1 ORDER BY 1;
\echo === Q1e: now
SELECT now() AT TIME ZONE 'America/New_York' AS now_et;
