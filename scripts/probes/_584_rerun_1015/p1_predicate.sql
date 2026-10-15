-- #584 RERUN 2026-10-15 p1: does the review's predicate count the population its action reads? (read-only)
BEGIN READ ONLY;
\echo === P0: the CURRENT predicate_sql, verbatim (threshold 20)
SELECT CASE WHEN NOT EXISTS (
                 SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'mi_universe_floor_shadow'
                   AND column_name = 'today_dollar_volume_at_open')
             THEN 0
             ELSE (SELECT COUNT(DISTINCT scan_date) FROM mi_universe_floor_shadow
                   WHERE (failed_price_floor OR failed_volume_floor)
                     AND today_dollar_volume_at_open IS NOT NULL) END AS current_predicate_reads;
\echo === P1: what the current predicate counts at each narrowing toward the action population (rejected side)
SELECT count(DISTINCT scan_date) FILTER (WHERE today_dollar_volume_at_open IS NOT NULL) dates_any_at_open_read,
       count(DISTINCT scan_date) FILTER (WHERE today_dollar_volume_at_open IS NOT NULL AND scan_date < DATE '2026-10-15') dates_excl_live_day,
       count(DISTINCT scan_date) FILTER (WHERE today_dollar_volume_at_open IS NOT NULL AND minutes_since_open_at_open <= 15) dates_in_window,
       count(DISTINCT scan_date) FILTER (WHERE minutes_since_open_at_open <= 15 AND today_dollar_volume_at_open >= 50000000) dates_with_a_50m_clearer,
       count(DISTINCT ticker) FILTER (WHERE minutes_since_open_at_open <= 15 AND today_dollar_volume_at_open >= 50000000) names_50m_in_window_any_settle_state
FROM mi_universe_floor_shadow WHERE (failed_price_floor OR failed_volume_floor);
\echo === P2: CORRECTED population per level: distinct rejected-side names, in-window (<=15 min) at-open dollar volume >= level, that SETTLED a 20-session close (simple), and CLEAN (+20 forward bars, 20 prior bars for ADR, no >4x close jump-up) = the action analysed sample
WITH cal AS (
  SELECT trade_date, (row_number() OVER (ORDER BY trade_date))::int rn
  FROM (SELECT DISTINCT trade_date FROM mi_daily_closes WHERE trade_date >= (SELECT MIN(scan_date) FROM mi_universe_floor_shadow)) x
), cand AS (
  SELECT s.ticker, s.scan_date, s.today_dollar_volume_at_open ao, c20.trade_date d20
  FROM mi_universe_floor_shadow s
  JOIN cal c0 ON c0.trade_date = s.scan_date
  JOIN cal c20 ON c20.rn = c0.rn + 20
  WHERE (s.failed_price_floor OR s.failed_volume_floor)
    AND s.minutes_since_open_at_open <= 15
    AND s.today_dollar_volume_at_open IS NOT NULL
), r AS (
  SELECT cand.*, f.n_fwd, f.maxq, f.c20,
         (SELECT count(*) FROM (SELECT 1 FROM mi_daily_closes d WHERE d.ticker = cand.ticker AND d.trade_date < cand.scan_date ORDER BY d.trade_date DESC LIMIT 20) z) n_pre
  FROM cand
  LEFT JOIN LATERAL (
    SELECT count(*) FILTER (WHERE w.trade_date > cand.scan_date) n_fwd, max(w.q) maxq,
           max(w.close) FILTER (WHERE w.trade_date = cand.d20) c20
    FROM (SELECT d.trade_date, d.close, d.close / NULLIF(lag(d.close) OVER (ORDER BY d.trade_date), 0) q
          FROM mi_daily_closes d WHERE d.ticker = cand.ticker AND d.trade_date BETWEEN cand.scan_date AND cand.d20) w) f ON true
)
SELECT lvl,
       count(DISTINCT ticker) FILTER (WHERE ao >= lvl AND c20 IS NOT NULL) AS names_with_20_session_close,
       count(DISTINCT ticker) FILTER (WHERE ao >= lvl AND c20 IS NOT NULL AND n_fwd = 20 AND n_pre = 20 AND COALESCE(maxq, 0) <= 4) AS names_clean_corrected_predicate
FROM r, (VALUES (10000000::float8), (25000000), (50000000), (100000000)) v(lvl)
GROUP BY lvl ORDER BY lvl;
\echo === P3: PROPOSED predicate_sql at the 100M level (the pending one), threshold 15
SELECT COUNT(DISTINCT ticker) FROM (
  WITH cal AS (
    SELECT trade_date, (row_number() OVER (ORDER BY trade_date))::int rn
    FROM (SELECT DISTINCT trade_date FROM mi_daily_closes
          WHERE trade_date >= (SELECT MIN(scan_date) FROM mi_universe_floor_shadow)) x
  )
  SELECT s.ticker
  FROM mi_universe_floor_shadow s
  JOIN cal c0  ON c0.trade_date = s.scan_date
  JOIN cal c20 ON c20.rn = c0.rn + 20
  JOIN LATERAL (
    SELECT count(*) FILTER (WHERE w.trade_date > s.scan_date) n_fwd, max(w.q) maxq,
           max(w.close) FILTER (WHERE w.trade_date = c20.trade_date) c20
    FROM (SELECT d.trade_date, d.close, d.close / NULLIF(lag(d.close) OVER (ORDER BY d.trade_date), 0) q
          FROM mi_daily_closes d
          WHERE d.ticker = s.ticker AND d.trade_date BETWEEN s.scan_date AND c20.trade_date) w) f ON true
  WHERE (s.failed_price_floor OR s.failed_volume_floor)
    AND s.minutes_since_open_at_open <= 15
    AND s.today_dollar_volume_at_open >= 100000000
    AND f.c20 IS NOT NULL AND f.n_fwd = 20 AND COALESCE(f.maxq, 0) <= 4
    AND (SELECT count(*) FROM (SELECT 1 FROM mi_daily_closes d
           WHERE d.ticker = s.ticker AND d.trade_date < s.scan_date
           ORDER BY d.trade_date DESC LIMIT 20) z) = 20
) t;
\echo === P4: same predicate shape at the 50M level (must equal the pipeline CLEAN count 19)
SELECT COUNT(DISTINCT ticker) FROM (
  WITH cal AS (
    SELECT trade_date, (row_number() OVER (ORDER BY trade_date))::int rn
    FROM (SELECT DISTINCT trade_date FROM mi_daily_closes
          WHERE trade_date >= (SELECT MIN(scan_date) FROM mi_universe_floor_shadow)) x
  )
  SELECT s.ticker
  FROM mi_universe_floor_shadow s
  JOIN cal c0  ON c0.trade_date = s.scan_date
  JOIN cal c20 ON c20.rn = c0.rn + 20
  JOIN LATERAL (
    SELECT count(*) FILTER (WHERE w.trade_date > s.scan_date) n_fwd, max(w.q) maxq,
           max(w.close) FILTER (WHERE w.trade_date = c20.trade_date) c20
    FROM (SELECT d.trade_date, d.close, d.close / NULLIF(lag(d.close) OVER (ORDER BY d.trade_date), 0) q
          FROM mi_daily_closes d
          WHERE d.ticker = s.ticker AND d.trade_date BETWEEN s.scan_date AND c20.trade_date) w) f ON true
  WHERE (s.failed_price_floor OR s.failed_volume_floor)
    AND s.minutes_since_open_at_open <= 15
    AND s.today_dollar_volume_at_open >= 50000000
    AND f.c20 IS NOT NULL AND f.n_fwd = 20 AND COALESCE(f.maxq, 0) <= 4
    AND (SELECT count(*) FROM (SELECT 1 FROM mi_daily_closes d
           WHERE d.ticker = s.ticker AND d.trade_date < s.scan_date
           ORDER BY d.trade_date DESC LIMIT 20) z) = 20
) t;
ROLLBACK;
