SET default_transaction_read_only = on;
-- #714 capture, file 60_fresh_block.sql. READ-ONLY, $0. Registered in docs/analysis/ep_float_neglect_prereg_2026-10-31.md
-- (frozen BEFORE any output of these files was read). Output = psql -A -F "|": each \echo '=== NAME' line
-- starts a section, the next line is its header row, then data rows, then a "(N rows)" footer.
-- Every ET conversion goes through AT TIME ZONE 'America/New_York'. Nothing here writes, locks or creates.
-- FRESH BLOCK F: scored rows with scan_date 2026-10-12..2026-10-30. No study has read these rows. Confirmation leg only:
-- it is read ONLY for a definition that reached PASS or LEAD on the main window (pre-registration section 10).

-- HARD DATE GATE (the #686 pattern): refuses before the fresh block's outcomes exist. The 15th NYSE session after
-- 2026-10-30 is 2026-11-20; its bar lands in mi_daily_closes that evening, so the earliest pull is 2026-11-21.
-- ON_ERROR_STOP=1 turns the division by zero into a hard stop; nothing is printed after it.
\echo '=== DATE_GATE'
SELECT CASE WHEN (now() AT TIME ZONE 'America/New_York')::date < DATE '2026-11-21'
  THEN 1 / ((now() AT TIME ZONE 'America/New_York')::date - (now() AT TIME ZONE 'America/New_York')::date) ELSE 1 END AS gate_passed;
\echo '=== FRESH_POP'
WITH lab(ticker, scan_date) AS (VALUES
  ('BFLY', DATE '2026-06-18'),
  ('PLTR', DATE '2026-08-04'),
  ('ABNB', DATE '2026-08-07'),
  ('TEAM', DATE '2026-08-07'),
  ('HTFL', DATE '2026-08-14'),
  ('MRNA', DATE '2026-08-19'),
  ('CHPT', DATE '2026-09-03'),
  ('PENG', DATE '2026-10-07')),
raw AS (
  SELECT l.* FROM mi_ep_scan_log l
  WHERE l.scan_date BETWEEN DATE '2026-10-12' AND DATE '2026-10-30' AND l.ep_score IS NOT NULL),
scored AS (
  SELECT DISTINCT ON (r.ticker, r.scan_date) r.*
  FROM raw r
  ORDER BY r.ticker, r.scan_date,
           (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC,
           r.ep_score DESC NULLS LAST, r.scan_time_et DESC NULLS LAST),
labrows AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l JOIN lab ON lab.ticker = l.ticker AND lab.scan_date = l.scan_date
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
pop AS (
  SELECT * FROM scored),
ticks AS (
  SELECT t.ticker, t.scan_date,
         count(*) AS n_ticks,
         count(*) FILTER (WHERE t.ep_score IS NOT NULL) AS n_scored_ticks,
         bool_or(t.filter_reason IS NULL AND t.score_tier IS NOT NULL) AS any_pass_tick,
         max(t.ep_score) AS max_score,
         max(t.float_shares) AS float_any_tick,
         count(t.float_shares) AS n_float_ticks,
         min(t.scan_time_et) AS first_tick_time,
         max(t.scan_time_et) AS last_tick_time,
         min(t.scan_time_et) FILTER (WHERE t.filter_reason IS NULL AND t.score_tier IS NOT NULL) AS first_pass_time,
         min(t.scan_time_et) FILTER (WHERE t.filter_reason IS NULL AND t.score_tier = 'HIGH') AS first_high_time
  FROM mi_ep_scan_log t
  WHERE (t.ticker, t.scan_date) IN (SELECT ticker, scan_date FROM pop)
  GROUP BY t.ticker, t.scan_date)
SELECT p.ticker, p.scan_date,
  (lab.ticker IS NOT NULL) AS is_labelled,
  (p.ep_score IS NOT NULL) AS is_scored,
  p.ep_score, p.score_tier, p.score_side, p.ep_bar, p.catalyst_quality, p.llm_catalyst_quality,
  regexp_replace(coalesce(p.filter_reason, ''), '[|\r\n]+', ' ', 'g') AS filter_reason,
  p.reject_stage, p.gap_pct, p.prev_close, p.current_price, p.rel_volume, p.pm_rvol, p.projected_vol_multiple,
  p.adv, p.adv_source, p.rank_by_gap, p.rank_by_prescore, p.minutes_since_open,
  substr((p.scan_time_et AT TIME ZONE 'America/New_York')::time::text, 1, 5) AS scan_time_et_hhmm,
  p.prev_day_volume, p.today_volume, p.days_since_prior_alert, p.extension_pct, p.quality_adv_dollar, p.atr_pct,
  p.market_cap, p.vol_percentile, p.prior_3m_change, p.float_shares,
  p.in_active_theme AS scan_in_active_theme, p.score_breakdown::text AS score_breakdown,
  t.n_ticks, t.n_scored_ticks, t.any_pass_tick, t.max_score, t.float_any_tick, t.n_float_ticks,
  substr((t.first_tick_time AT TIME ZONE 'America/New_York')::time::text, 1, 5) AS first_tick_hhmm, substr((t.last_tick_time AT TIME ZONE 'America/New_York')::time::text, 1, 5) AS last_tick_hhmm,
  substr((t.first_pass_time AT TIME ZONE 'America/New_York')::time::text, 1, 5) AS first_pass_hhmm, substr((t.first_high_time AT TIME ZONE 'America/New_York')::time::text, 1, 5) AS first_high_hhmm,
  a.id AS alert_id, a.score_tier AS alert_tier, a.ep_score AS alert_score, a.catalyst_quality AS alert_catalyst_quality,
  a.catalyst_type, a.judge_tier, a.judge_grade, a.setup_class, a.rubric_version,
  ah.any_high_alert, ah.n_live_alerts,
  rk.expct_scheduled, rk.expct_scheduled_src, rk.expct_looking, rk.expct_beat, rk.expct_growth_yoy_pct,
  rk.expct_combined_class, rk.base_days_raw40, rk.base_depth_raw40, rk.base_days_adr6, rk.base_depth_adr6,
  rk.base_lookback_bars, rk.ext_xadr_pregap,
  cm.q_revenue_yoy_pct, cm.extraction_quality,
  oc.baseline_close AS outcome_baseline_close, oc.fwd_5d_pct, oc.fwd_10d_pct, oc.n_sessions_5d, oc.n_sessions_10d,
  mc.market_cap AS market_cap_snapshot, (mc.fetched_at AT TIME ZONE 'America/New_York')::date AS market_cap_snapshot_date,
  st.security_type, so.sector, so.industry
FROM pop p
LEFT JOIN lab ON lab.ticker = p.ticker AND lab.scan_date = p.scan_date
LEFT JOIN ticks t ON t.ticker = p.ticker AND t.scan_date = p.scan_date
LEFT JOIN LATERAL (
  SELECT x.id, x.score_tier, x.ep_score, x.catalyst_quality, x.catalyst_type, x.judge_tier, x.judge_grade,
         x.setup_class, x.rubric_version
  FROM mi_ep_alerts x
  WHERE x.ticker = p.ticker AND x.alert_date = p.scan_date AND COALESCE(x.source, 'live') = 'live'
  ORDER BY x.created_at LIMIT 1) a ON TRUE
LEFT JOIN LATERAL (
  SELECT bool_or(x.score_tier = 'HIGH') AS any_high_alert, count(*) AS n_live_alerts
  FROM mi_ep_alerts x
  WHERE x.ticker = p.ticker AND x.alert_date = p.scan_date AND COALESCE(x.source, 'live') = 'live') ah ON TRUE
LEFT JOIN LATERAL (
  SELECT r.expct_scheduled, r.expct_scheduled_src, r.expct_looking, r.expct_beat, r.expct_growth_yoy_pct,
         r.expct_combined_class, r.base_days_raw40, r.base_depth_raw40, r.base_days_adr6, r.base_depth_adr6,
         r.base_lookback_bars, r.ext_xadr_pregap
  FROM mi_alert_rank_shadow r
  WHERE r.ticker = p.ticker AND r.alert_date = p.scan_date ORDER BY r.computed_at DESC LIMIT 1) rk ON TRUE
LEFT JOIN LATERAL (
  SELECT c.q_revenue_yoy_pct, c.extraction_quality FROM mi_ep_catalyst_metrics c
  WHERE c.ticker = p.ticker AND c.alert_date = p.scan_date ORDER BY c.extracted_at DESC LIMIT 1) cm ON TRUE
LEFT JOIN mi_ep_scan_outcomes oc ON oc.ticker = p.ticker AND oc.scan_date = p.scan_date
LEFT JOIN mi_market_caps mc ON mc.ticker = p.ticker
LEFT JOIN mi_security_types st ON st.ticker = p.ticker
LEFT JOIN mi_ticker_overrides so ON so.ticker = p.ticker
ORDER BY p.scan_date, p.ticker;
\echo '=== FRESH_BARS'
WITH lab(ticker, scan_date) AS (VALUES
  ('BFLY', DATE '2026-06-18'),
  ('PLTR', DATE '2026-08-04'),
  ('ABNB', DATE '2026-08-07'),
  ('TEAM', DATE '2026-08-07'),
  ('HTFL', DATE '2026-08-14'),
  ('MRNA', DATE '2026-08-19'),
  ('CHPT', DATE '2026-09-03'),
  ('PENG', DATE '2026-10-07')),
raw AS (
  SELECT l.* FROM mi_ep_scan_log l
  WHERE l.scan_date BETWEEN DATE '2026-10-12' AND DATE '2026-10-30' AND l.ep_score IS NOT NULL),
scored AS (
  SELECT DISTINCT ON (r.ticker, r.scan_date) r.*
  FROM raw r
  ORDER BY r.ticker, r.scan_date,
           (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC,
           r.ep_score DESC NULLS LAST, r.scan_time_et DESC NULLS LAST),
labrows AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l JOIN lab ON lab.ticker = l.ticker AND lab.scan_date = l.scan_date
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
pop AS (
  SELECT * FROM scored),
pop_tk AS (SELECT DISTINCT ticker FROM pop)
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM mi_daily_closes d
WHERE d.trade_date >= DATE '2021-01-01' AND (d.ticker IN (SELECT ticker FROM pop_tk) OR d.ticker IN ('SPY', 'QQQ', 'IWM'))
ORDER BY d.ticker, d.trade_date;
\echo '=== FRESH_FETCH'
-- rows with no stored float on any tick
WITH lab(ticker, scan_date) AS (VALUES
  ('BFLY', DATE '2026-06-18'),
  ('PLTR', DATE '2026-08-04'),
  ('ABNB', DATE '2026-08-07'),
  ('TEAM', DATE '2026-08-07'),
  ('HTFL', DATE '2026-08-14'),
  ('MRNA', DATE '2026-08-19'),
  ('CHPT', DATE '2026-09-03'),
  ('PENG', DATE '2026-10-07')),
raw AS (
  SELECT l.* FROM mi_ep_scan_log l
  WHERE l.scan_date BETWEEN DATE '2026-10-12' AND DATE '2026-10-30' AND l.ep_score IS NOT NULL),
scored AS (
  SELECT DISTINCT ON (r.ticker, r.scan_date) r.*
  FROM raw r
  ORDER BY r.ticker, r.scan_date,
           (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC,
           r.ep_score DESC NULLS LAST, r.scan_time_et DESC NULLS LAST),
labrows AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l JOIN lab ON lab.ticker = l.ticker AND lab.scan_date = l.scan_date
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
pop AS (
  SELECT * FROM scored),
ticks AS (
  SELECT t.ticker, t.scan_date,
         count(*) AS n_ticks,
         count(*) FILTER (WHERE t.ep_score IS NOT NULL) AS n_scored_ticks,
         bool_or(t.filter_reason IS NULL AND t.score_tier IS NOT NULL) AS any_pass_tick,
         max(t.ep_score) AS max_score,
         max(t.float_shares) AS float_any_tick,
         count(t.float_shares) AS n_float_ticks,
         min(t.scan_time_et) AS first_tick_time,
         max(t.scan_time_et) AS last_tick_time,
         min(t.scan_time_et) FILTER (WHERE t.filter_reason IS NULL AND t.score_tier IS NOT NULL) AS first_pass_time,
         min(t.scan_time_et) FILTER (WHERE t.filter_reason IS NULL AND t.score_tier = 'HIGH') AS first_high_time
  FROM mi_ep_scan_log t
  WHERE (t.ticker, t.scan_date) IN (SELECT ticker, scan_date FROM pop)
  GROUP BY t.ticker, t.scan_date)
SELECT p.ticker, p.scan_date
FROM pop p JOIN ticks t ON t.ticker = p.ticker AND t.scan_date = p.scan_date
WHERE COALESCE(p.float_shares, t.float_any_tick) IS NULL ORDER BY p.scan_date, p.ticker;
\echo '=== FRESH_SPLITS'
WITH lab(ticker, scan_date) AS (VALUES
  ('BFLY', DATE '2026-06-18'),
  ('PLTR', DATE '2026-08-04'),
  ('ABNB', DATE '2026-08-07'),
  ('TEAM', DATE '2026-08-07'),
  ('HTFL', DATE '2026-08-14'),
  ('MRNA', DATE '2026-08-19'),
  ('CHPT', DATE '2026-09-03'),
  ('PENG', DATE '2026-10-07')),
raw AS (
  SELECT l.* FROM mi_ep_scan_log l
  WHERE l.scan_date BETWEEN DATE '2026-10-12' AND DATE '2026-10-30' AND l.ep_score IS NOT NULL),
scored AS (
  SELECT DISTINCT ON (r.ticker, r.scan_date) r.*
  FROM raw r
  ORDER BY r.ticker, r.scan_date,
           (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC,
           r.ep_score DESC NULLS LAST, r.scan_time_et DESC NULLS LAST),
labrows AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l JOIN lab ON lab.ticker = l.ticker AND lab.scan_date = l.scan_date
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
pop AS (
  SELECT * FROM scored),
pop_tk AS (SELECT DISTINCT ticker FROM pop)
SELECT sp.ticker, sp.execution_date, sp.split_from, sp.split_to, sp.adjustment_applied, sp.adjustment_outcome, sp.applied_factor
FROM mi_splits sp WHERE sp.ticker IN (SELECT ticker FROM pop_tk) AND sp.execution_date >= DATE '2021-01-01'
ORDER BY sp.ticker, sp.execution_date;
