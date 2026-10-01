\echo === Q1a: all rows by scan_date
SELECT scan_date, count(*) rows, count(*) FILTER (WHERE failed_price_floor OR failed_volume_floor) rejected,
  count(*) FILTER (WHERE NOT (failed_price_floor OR failed_volume_floor)) admitted,
  count(*) FILTER (WHERE (failed_price_floor OR failed_volume_floor) AND today_dollar_volume_at_open IS NOT NULL) rej_atopen,
  count(*) FILTER (WHERE (failed_price_floor OR failed_volume_floor) AND today_dollar_volume_at_open IS NULL AND today_dollar_volume_last IS NOT NULL AND minutes_since_open_last<=15) rej_fallback_last15,
  count(*) FILTER (WHERE NOT (failed_price_floor OR failed_volume_floor) AND today_dollar_volume_at_open IS NOT NULL) adm_atopen,
  min(minutes_since_open_at_open) mn_open, max(minutes_since_open_at_open) mx_open
FROM mi_universe_floor_shadow GROUP BY 1 ORDER BY 1;
\echo === Q1b: overall
SELECT count(*), count(DISTINCT scan_date) dates, min(scan_date), max(scan_date), count(DISTINCT ticker) names,
 count(*) FILTER (WHERE failed_price_floor OR failed_volume_floor) rej,
 count(*) FILTER (WHERE failed_price_floor AND NOT failed_volume_floor) P,
 count(*) FILTER (WHERE failed_volume_floor AND NOT failed_price_floor) V,
 count(*) FILTER (WHERE failed_volume_floor AND failed_price_floor) PV
FROM mi_universe_floor_shadow;
\echo === Q1c: distribution of minutes_since_open_at_open for rejected rows with at_open dv
SELECT minutes_since_open_at_open m, count(*) FROM mi_universe_floor_shadow WHERE (failed_price_floor OR failed_volume_floor) AND today_dollar_volume_at_open IS NOT NULL GROUP BY 1 ORDER BY 1;
\echo === Q1d: rejected rows without at_open: reasons
SELECT (minutes_since_open_at_open IS NULL) no_open_min, (today_dollar_volume_at_open IS NULL) no_dv_open, (today_dollar_volume_last IS NULL) no_dv_last, (minutes_since_open_last IS NULL) no_min_last, count(*) FROM mi_universe_floor_shadow WHERE failed_price_floor OR failed_volume_floor GROUP BY 1,2,3,4 ORDER BY 5 DESC;
\echo === Q1e: acting floors distinct
SELECT acting_price_floor, acting_volume_floor, min(scan_date), max(scan_date), count(*) FROM mi_universe_floor_shadow GROUP BY 1,2;
\echo === Q1f: when did today_* cols start populating
SELECT min(scan_date) FILTER (WHERE today_dollar_volume_at_open IS NOT NULL), max(scan_date) FILTER (WHERE today_dollar_volume_at_open IS NOT NULL), min(scan_date) FILTER (WHERE today_dollar_volume_last IS NOT NULL) FROM mi_universe_floor_shadow;
\echo === Q1g: mi_daily_closes coverage
SELECT min(trade_date), max(trade_date), count(DISTINCT trade_date) FROM mi_daily_closes;
