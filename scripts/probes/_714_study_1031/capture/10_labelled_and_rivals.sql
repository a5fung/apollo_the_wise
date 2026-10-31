SET default_transaction_read_only = on;
-- #714 capture, file 10_labelled_and_rivals.sql. READ-ONLY, $0. Registered in docs/analysis/ep_float_neglect_prereg_2026-10-31.md
-- (frozen BEFORE any output of these files was read). Output = psql -A -F "|": each \echo '=== NAME' line
-- starts a section, the next line is its header row, then data rows, then a "(N rows)" footer.
-- Every ET conversion goes through AT TIME ZONE 'America/New_York'. Nothing here writes, locks or creates.
-- POPULATION A. The 8 labelled EPs, every tick they logged, and every logged ticker on their 7 boards.

\echo '=== LABELLED_TICKS'
-- every scan-log tick of the 8 labelled EPs; ABNB/CHPT were filtered, so ep_score may be NULL
WITH lab(ticker, scan_date) AS (VALUES
  ('BFLY', DATE '2026-06-18'),
  ('PLTR', DATE '2026-08-04'),
  ('ABNB', DATE '2026-08-07'),
  ('TEAM', DATE '2026-08-07'),
  ('HTFL', DATE '2026-08-14'),
  ('MRNA', DATE '2026-08-19'),
  ('CHPT', DATE '2026-09-03'),
  ('PENG', DATE '2026-10-07'))
SELECT l.ticker, l.scan_date, l.id AS scan_row_id,
  substr((l.scan_time_et AT TIME ZONE 'America/New_York')::time::text, 1, 5) AS scan_time_et_hhmm, l.minutes_since_open,
  regexp_replace(coalesce(l.filter_reason, ''), '[|\r\n]+', ' ', 'g') AS filter_reason, l.reject_stage,
  l.ep_score, l.score_tier, l.score_side, l.ep_bar, l.catalyst_quality, l.llm_catalyst_quality,
  l.gap_pct, l.gap_pct_rt, l.gap_pct_delayed, l.prev_close, l.current_price, l.price_source,
  l.rel_volume, l.pm_rvol, l.projected_vol_multiple, l.adv, l.adv_source, l.quality_adv_dollar, l.atr_pct,
  l.market_cap, l.float_shares, l.prior_3m_change, l.rank_by_gap, l.rank_by_prescore,
  l.score_breakdown::text AS score_breakdown
FROM mi_ep_scan_log l JOIN lab ON lab.ticker = l.ticker AND lab.scan_date = l.scan_date
ORDER BY l.scan_date, l.ticker, l.scan_time_et;
\echo '=== BOARD_ALL'
-- one row per LOGGED ticker on the 8 labelled dates; is_scored=1 rows are the primary rival set R1
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
  WHERE l.scan_date BETWEEN DATE '2026-05-01' AND DATE '2026-10-09' AND l.ep_score IS NOT NULL),
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
  SELECT * FROM scored
  UNION ALL
  SELECT * FROM labrows lr
  WHERE NOT EXISTS (SELECT 1 FROM scored s WHERE s.ticker = lr.ticker AND s.scan_date = lr.scan_date)),
board_all AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l
  WHERE l.scan_date IN (SELECT DISTINCT scan_date FROM lab)
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
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
  WHERE (t.ticker, t.scan_date) IN (SELECT ticker, scan_date FROM board_all)
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
FROM board_all p
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
