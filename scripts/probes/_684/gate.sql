-- #684 STEP 0 — POPULATION GATE (composition only; NO forward bars, NO outcomes anywhere in this file).
-- Population = every gap-day candidate the EP scan SCORED (ep_score NOT NULL) in mi_ep_scan_log,
-- scan_date 2026-05-01 .. the last scan_date with >= 15 later sessions in mi_daily_closes,
-- ONE row per (ticker, scan_date).
-- DEDUPE RULE (stated): prefer the row that ALERTED (filter_reason IS NULL AND score_tier IS NOT NULL);
-- else the tick with the HIGHEST ep_score; ties -> the latest scan_time_et.  Sensitivity to a
-- "last tick of the day" rule is reported below (rows whose admission would differ).
-- Read-only. $0.
\pset format unaligned
\pset fieldsep '|'
WITH sess AS (
  SELECT trade_date FROM mi_daily_closes GROUP BY trade_date HAVING count(*) >= 500
), last_ok AS (
  SELECT max(s.trade_date) AS d FROM sess s
  WHERE (SELECT count(*) FROM sess s2 WHERE s2.trade_date > s.trade_date) >= 15
), raw AS (
  SELECT l.*, (l.created_at AT TIME ZONE 'America/New_York')::date - l.scan_date AS lag_days,
         CASE WHEN l.scan_date < DATE '2026-08-22' THEN 'A' ELSE 'B' END AS era
  FROM mi_ep_scan_log l
  WHERE l.scan_date BETWEEN DATE '2026-05-01' AND (SELECT d FROM last_ok)
    AND l.ep_score IS NOT NULL
), ticks AS (
  SELECT ticker, scan_date, count(*) AS n_ticks,
         bool_or(filter_reason IS NULL AND score_tier IS NOT NULL) AS any_pass_tick,
         max(ep_score) AS max_score, min(ep_score) AS min_score
  FROM raw GROUP BY ticker, scan_date
), dedup AS (
  SELECT DISTINCT ON (ticker, scan_date) r.*
  FROM raw r
  ORDER BY ticker, scan_date, (filter_reason IS NULL AND score_tier IS NOT NULL) DESC, ep_score DESC, scan_time_et DESC
), lasttick AS (
  SELECT DISTINCT ON (ticker, scan_date) r.ticker, r.scan_date, r.ep_score AS last_score,
         (filter_reason IS NULL AND score_tier IS NOT NULL) AS last_pass
  FROM raw r ORDER BY ticker, scan_date, scan_time_et DESC
), alerts AS (
  SELECT DISTINCT ON (ticker, alert_date) ticker, alert_date, score_tier, ep_score, gap_pct, created_at
  FROM mi_ep_alerts
  WHERE alert_date BETWEEN DATE '2026-05-01' AND DATE '2026-09-11' AND COALESCE(source,'live')='live'
  ORDER BY ticker, alert_date, created_at
), pop AS (
  SELECT d.*, t.n_ticks, t.any_pass_tick, t.max_score, t.min_score,
         (a.ticker IS NOT NULL) AS alerted,
         CASE WHEN prev_close < 5 THEN '1_lt5' WHEN prev_close < 20 THEN '2_5to20' WHEN prev_close < 100 THEN '3_20to100' ELSE '4_100plus' END AS price_band
  FROM dedup d
  JOIN ticks t USING (ticker, scan_date)
  LEFT JOIN (SELECT DISTINCT ON (ticker, alert_date) ticker, alert_date FROM mi_ep_alerts
             WHERE COALESCE(source,'live')='live' ORDER BY ticker, alert_date) a
    ON a.ticker = d.ticker AND a.alert_date = d.scan_date
)
SELECT 'window' AS k, 'first_scan_date' AS sub, min(scan_date)::text AS v FROM pop
UNION ALL SELECT 'window', 'last_scan_date_with_15_fwd_sessions', (SELECT d FROM last_ok)::text
UNION ALL SELECT 'window', 'sessions_in_mi_daily_closes_after_last_ok', (SELECT count(*) FROM sess WHERE trade_date > (SELECT d FROM last_ok))::text
UNION ALL SELECT 'window', 'last_session_in_mi_daily_closes', (SELECT max(trade_date) FROM sess)::text
UNION ALL SELECT 'raw', 'scored_ticks_total', count(*)::text FROM raw
UNION ALL SELECT 'raw', 'scored_ticks_era_'||era, count(*)::text FROM raw GROUP BY era
UNION ALL SELECT 'raw', 'lag_days_'||lag_days::text, count(*)::text FROM raw GROUP BY lag_days
UNION ALL SELECT 'raw', 'score_side_'||COALESCE(score_side,'NULL'), count(*)::text FROM raw GROUP BY score_side
UNION ALL SELECT 'raw', 'reject_stage_'||COALESCE(reject_stage,'NULL'), count(*)::text FROM raw GROUP BY reject_stage
UNION ALL SELECT 'raw', 'filter_prefix_'||COALESCE(left(filter_reason, 22),'NULL(pass)'), count(*)::text FROM raw GROUP BY left(filter_reason, 22)
UNION ALL SELECT 'raw', 'ticks_per_pair_'||least(n_ticks,10)::text, count(*)::text FROM ticks GROUP BY least(n_ticks,10)
UNION ALL SELECT 'pop', 'n_total', count(*)::text FROM pop
UNION ALL SELECT 'pop', 'n_names', count(DISTINCT ticker)::text FROM pop
UNION ALL SELECT 'pop', 'n_scan_dates', count(DISTINCT scan_date)::text FROM pop
UNION ALL SELECT 'pop', 'month_'||to_char(scan_date,'YYYY-MM'), count(*)::text FROM pop GROUP BY to_char(scan_date,'YYYY-MM')
UNION ALL SELECT 'pop', 'era_'||era, count(*)::text FROM pop GROUP BY era
UNION ALL SELECT 'pop', 'era_'||era||'_alerted_'||alerted::text, count(*)::text FROM pop GROUP BY era, alerted
UNION ALL SELECT 'pop', 'era_'||era||'_tier_'||COALESCE(score_tier,'none'), count(*)::text FROM pop GROUP BY era, score_tier
UNION ALL SELECT 'pop', 'era_'||era||'_scoreband_'||CASE WHEN ep_score<50 THEN '0_lt50' WHEN ep_score<65 THEN '1_50to65' WHEN ep_score<80 THEN '2_65to80' ELSE '3_80plus' END, count(*)::text FROM pop GROUP BY era, 2
UNION ALL SELECT 'pop', 'price_'||price_band, count(*)::text FROM pop GROUP BY price_band
UNION ALL SELECT 'pop', 'price_'||price_band||'_alerted_'||alerted::text, count(*)::text FROM pop GROUP BY price_band, alerted
UNION ALL SELECT 'pop', 'prev_close_null', count(*)::text FROM pop WHERE prev_close IS NULL
UNION ALL SELECT 'pop', 'median_prev_close', round(percentile_cont(0.5) WITHIN GROUP (ORDER BY prev_close)::numeric,2)::text FROM pop
UNION ALL SELECT 'pop', 'median_gap_pct_all', round(percentile_cont(0.5) WITHIN GROUP (ORDER BY gap_pct)::numeric,2)::text FROM pop
UNION ALL SELECT 'pop', 'median_gap_pct_alerted_'||alerted::text, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY gap_pct)::numeric,2)::text FROM pop GROUP BY alerted
UNION ALL SELECT 'pop', 'median_ep_score_alerted_'||alerted::text, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY ep_score)::numeric,1)::text FROM pop GROUP BY alerted
UNION ALL SELECT 'pop', 'notalerted_reject_stage_'||COALESCE(reject_stage,'NULL'), count(*)::text FROM pop WHERE NOT alerted GROUP BY reject_stage
UNION ALL SELECT 'pop', 'notalerted_filter_prefix_'||COALESCE(left(filter_reason, 22),'NULL'), count(*)::text FROM pop WHERE NOT alerted GROUP BY left(filter_reason, 22)
UNION ALL SELECT 'pop', 'notalerted_but_had_pass_tick', count(*)::text FROM pop WHERE NOT alerted AND any_pass_tick
UNION ALL SELECT 'pop', 'alerted_but_chosen_row_not_pass', count(*)::text FROM pop WHERE alerted AND NOT (filter_reason IS NULL AND score_tier IS NOT NULL)
UNION ALL SELECT 'pop', 'catalyst_quality_'||COALESCE(catalyst_quality,'NULL'), count(*)::text FROM pop GROUP BY catalyst_quality
UNION ALL SELECT 'pop', 'in_active_theme_'||COALESCE(in_active_theme::text,'NULL'), count(*)::text FROM pop GROUP BY in_active_theme
UNION ALL SELECT 'pop', 'era_'||era||'_extension_pct_filled', count(extension_pct)::text FROM pop GROUP BY era
UNION ALL SELECT 'pop', 'era_'||era||'_market_cap_filled', count(market_cap)::text FROM pop GROUP BY era
UNION ALL SELECT 'pop', 'era_'||era||'_float_filled', count(float_shares)::text FROM pop GROUP BY era
UNION ALL SELECT 'pop', 'era_'||era||'_atr_pct_filled', count(atr_pct)::text FROM pop GROUP BY era
UNION ALL SELECT 'pop', 'era_'||era||'_prior_3m_filled', count(prior_3m_change)::text FROM pop GROUP BY era
UNION ALL SELECT 'pop', 'era_'||era||'_adv_filled', count(adv)::text FROM pop GROUP BY era
UNION ALL SELECT 'pop', 'era_'||era||'_rel_volume_filled', count(rel_volume)::text FROM pop GROUP BY era
UNION ALL SELECT 'pop', 'era_'||era||'_score_breakdown_filled', count(score_breakdown)::text FROM pop GROUP BY era
UNION ALL SELECT 'dedupe', 'pairs_where_last_tick_admission_differs', count(*)::text FROM pop p JOIN lasttick lt USING (ticker, scan_date) WHERE lt.last_pass <> (p.filter_reason IS NULL AND p.score_tier IS NOT NULL)
UNION ALL SELECT 'dedupe', 'pairs_where_max_minus_min_score_gt_10', count(*)::text FROM pop WHERE max_score - min_score > 10
UNION ALL SELECT 'recon', 'alerts_0501_0911_live', count(*)::text FROM alerts
UNION ALL SELECT 'recon', 'alerts_0501_0911_live_pre0822', count(*)::text FROM alerts WHERE alert_date < DATE '2026-08-22'
UNION ALL SELECT 'recon', 'alerts_within_pop_window', count(*)::text FROM alerts WHERE alert_date <= (SELECT d FROM last_ok)
UNION ALL SELECT 'recon', 'alerts_within_window_with_scored_row', count(*)::text FROM alerts a WHERE a.alert_date <= (SELECT d FROM last_ok) AND EXISTS (SELECT 1 FROM pop p WHERE p.ticker=a.ticker AND p.scan_date=a.alert_date)
UNION ALL SELECT 'recon', 'alert_NO_scored_row_'||a.ticker||'_'||a.alert_date::text, COALESCE(a.score_tier,'?')||'/'||COALESCE(a.ep_score::text,'?') FROM alerts a WHERE a.alert_date <= (SELECT d FROM last_ok) AND NOT EXISTS (SELECT 1 FROM pop p WHERE p.ticker=a.ticker AND p.scan_date=a.alert_date)
UNION ALL SELECT 'recon', 'alert_past_window_'||a.ticker||'_'||a.alert_date::text, COALESCE(a.score_tier,'?') FROM alerts a WHERE a.alert_date > (SELECT d FROM last_ok)
UNION ALL SELECT 'recon', 'pop_alerted_rows_total', count(*)::text FROM pop WHERE alerted
UNION ALL SELECT 'recon', 'pop_alerted_rows_not_in_0501_0911_alerts', count(*)::text FROM pop p WHERE alerted AND NOT EXISTS (SELECT 1 FROM alerts a WHERE a.ticker=p.ticker AND a.alert_date=p.scan_date)
UNION ALL SELECT 'labelled', t.ticker||'_'||t.d::text||'_in_pop', COALESCE((SELECT 'yes alerted='||p.alerted::text||' score='||p.ep_score::text||' reason='||COALESCE(left(p.filter_reason,40),'NULL') FROM pop p WHERE p.ticker=t.ticker AND p.scan_date=t.d), 'NO')
  FROM (VALUES ('BFLY',DATE '2026-06-18'),('PLTR',DATE '2026-08-04'),('ABNB',DATE '2026-08-07'),('TEAM',DATE '2026-08-07'),('HTFL',DATE '2026-08-14'),('MRNA',DATE '2026-08-19'),('CHPT',DATE '2026-09-03')) t(ticker,d)
UNION ALL SELECT 'labelled', t.ticker||'_'||t.d::text||'_any_scanlog_row', COALESCE((SELECT count(*)::text||' rows, scored='||count(ep_score)::text||', reasons='||string_agg(DISTINCT COALESCE(left(filter_reason,30),'pass'), ';') FROM mi_ep_scan_log l WHERE l.ticker=t.ticker AND l.scan_date=t.d), 'NONE')
  FROM (VALUES ('BFLY',DATE '2026-06-18'),('PLTR',DATE '2026-08-04'),('ABNB',DATE '2026-08-07'),('TEAM',DATE '2026-08-07'),('HTFL',DATE '2026-08-14'),('MRNA',DATE '2026-08-19'),('CHPT',DATE '2026-09-03')) t(ticker,d)
ORDER BY 1, 2;
