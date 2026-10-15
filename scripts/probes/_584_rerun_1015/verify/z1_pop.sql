-- #584 10-15 VERIFIER (Opus, independent of the reader's pipeline; read-only). Population first.
BEGIN READ ONLY;
\echo === Z1a: base (scan_date <= 10-14), side split, null flags
SELECT count(*) rows_, count(DISTINCT ticker) names, count(DISTINCT scan_date) dates, min(scan_date), max(scan_date),
  count(*) FILTER (WHERE failed_price_floor IS NULL OR failed_volume_floor IS NULL) null_flags,
  count(*) FILTER (WHERE failed_price_floor OR failed_volume_floor) rej_rows,
  count(DISTINCT ticker) FILTER (WHERE failed_price_floor OR failed_volume_floor) rej_names,
  count(*) FILTER (WHERE NOT (failed_price_floor OR failed_volume_floor)) adm_rows,
  count(DISTINCT ticker) FILTER (WHERE NOT (failed_price_floor OR failed_volume_floor)) adm_names
FROM mi_universe_floor_shadow WHERE scan_date <= DATE '2026-10-14';
\echo === Z1b: rows on/after 10-15 (live session, excluded)
SELECT scan_date, count(*) FROM mi_universe_floor_shadow WHERE scan_date > DATE '2026-10-14' GROUP BY 1 ORDER BY 1;
\echo === Z1c: acting floors
SELECT acting_price_floor, acting_volume_floor, min(scan_date), max(scan_date), count(*) FROM mi_universe_floor_shadow WHERE scan_date <= DATE '2026-10-14' GROUP BY 1,2;
\echo === Z1d: backfill/test signature (created_at ET date vs scan_date)
SELECT count(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::date <> scan_date) created_ne_scan,
       count(*) FILTER (WHERE created_at IS NULL) created_null,
       count(*) FILTER (WHERE (first_seen_et AT TIME ZONE 'America/New_York')::date <> scan_date) first_ne_scan
FROM mi_universe_floor_shadow WHERE scan_date <= DATE '2026-10-14';
\echo === Z1e: in-window (at_open read, minutes <= 15) by side; admitted gap>=10
SELECT (failed_price_floor OR failed_volume_floor) rej, count(*) rows_, count(DISTINCT ticker) names,
  count(*) FILTER (WHERE gap_pct_at_open >= 10) g10_rows, count(DISTINCT ticker) FILTER (WHERE gap_pct_at_open >= 10) g10_names,
  count(*) FILTER (WHERE minutes_since_open_at_open = 1) min1_rows
FROM mi_universe_floor_shadow WHERE scan_date <= DATE '2026-10-14' AND today_dollar_volume_at_open IS NOT NULL AND minutes_since_open_at_open <= 15 GROUP BY 1;
\echo === Z1f: rejected rows with NO at_open read; fallback-eligible (_last <= 15 min)
SELECT count(*) FILTER (WHERE today_dollar_volume_at_open IS NULL) no_atopen,
       count(*) FILTER (WHERE today_dollar_volume_at_open IS NULL AND today_dollar_volume_last IS NOT NULL AND minutes_since_open_last <= 15) fallback_eligible
FROM mi_universe_floor_shadow WHERE scan_date <= DATE '2026-10-14' AND (failed_price_floor OR failed_volume_floor);
\echo === Z1g: duplicate daily bars on (ticker, trade_date) since 07-01
SELECT count(*) FROM (SELECT ticker, trade_date FROM mi_daily_closes WHERE trade_date >= DATE '2026-07-01' GROUP BY 1,2 HAVING count(*) > 1) x;
\echo === Z1h: last close date ingested + thin dates since 07-01
SELECT max(trade_date) FROM mi_daily_closes;
SELECT trade_date, count(*) FROM mi_daily_closes WHERE trade_date >= DATE '2026-07-01' GROUP BY 1 HAVING count(*) < 5000 ORDER BY 1;
\echo === Z1i: the CURRENT predicate_sql verbatim
SELECT CASE WHEN NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_name = 'mi_universe_floor_shadow'
             AND column_name = 'today_dollar_volume_at_open')
       THEN 0
       ELSE (SELECT COUNT(DISTINCT scan_date) FROM mi_universe_floor_shadow
             WHERE (failed_price_floor OR failed_volume_floor)
               AND today_dollar_volume_at_open IS NOT NULL) END AS current_predicate;
ROLLBACK;
