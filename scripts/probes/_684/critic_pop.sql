-- #684 CRITIC — independent population re-derivation (read-only, $0). Written without reusing gate.sql.
-- Window end derived independently: the trading date (>= 500 tickers in mi_daily_closes) that has exactly
-- 15 later trading dates.
\pset format unaligned
\pset fieldsep '|'
\pset footer off
WITH d AS (
  SELECT trade_date FROM mi_daily_closes WHERE trade_date >= DATE '2026-07-01'
  GROUP BY trade_date HAVING count(*) >= 500
), endd AS (
  SELECT trade_date AS e FROM d ORDER BY trade_date DESC OFFSET 15 LIMIT 1
), t AS (
  SELECT l.ticker, l.scan_date, l.ep_score, l.filter_reason, l.score_tier, l.scan_time_et, l.created_at,
         (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) AS is_pass
  FROM mi_ep_scan_log l, endd
  WHERE l.scan_date >= DATE '2026-05-01' AND l.scan_date <= endd.e AND l.ep_score IS NOT NULL
), pr AS (
  SELECT ticker, scan_date, count(*) n_ticks, bool_or(is_pass) any_pass,
         bool_or(filter_reason IS NULL) any_null_reason,
         bool_or(score_tier IS NOT NULL) any_tier
  FROM t GROUP BY 1, 2
), al AS (
  SELECT ticker, alert_date, count(*) n_rows, min(created_at) first_created
  FROM mi_ep_alerts WHERE COALESCE(source, 'live') = 'live' GROUP BY 1, 2
)
SELECT 'end_date', (SELECT e FROM endd)::text
UNION ALL SELECT 'scored_ticks', count(*)::text FROM t
UNION ALL SELECT 'pairs', count(*)::text FROM pr
UNION ALL SELECT 'names', count(DISTINCT ticker)::text FROM pr
UNION ALL SELECT 'scan_dates', count(DISTINCT scan_date)::text FROM pr
UNION ALL SELECT 'pairs_any_pass', count(*)::text FROM pr WHERE any_pass
UNION ALL SELECT 'pairs_null_reason_but_no_tier', count(*)::text FROM pr WHERE any_null_reason AND NOT any_pass
UNION ALL SELECT 'ticks_tier_set_but_reason_set', count(*)::text FROM t WHERE score_tier IS NOT NULL AND filter_reason IS NOT NULL
UNION ALL SELECT 'ticks_reason_not_score_prefix', count(*)::text FROM t WHERE filter_reason IS NOT NULL AND filter_reason !~ '^score -?[0-9.]+ < '
UNION ALL SELECT 'reason_not_score_prefix_sample:' || left(filter_reason, 40), count(*)::text FROM t WHERE filter_reason IS NOT NULL AND filter_reason !~ '^score -?[0-9.]+ < ' GROUP BY left(filter_reason, 40)
UNION ALL SELECT 'ticks_created_not_same_et_day', count(*)::text FROM t WHERE (created_at AT TIME ZONE 'America/New_York')::date <> scan_date
UNION ALL SELECT 'ticks_scan_time_not_same_et_day', count(*)::text FROM t WHERE (scan_time_et AT TIME ZONE 'America/New_York')::date <> scan_date
UNION ALL SELECT 'dup_ticks_same_ticker_same_time', count(*)::text FROM (SELECT ticker, scan_time_et FROM t GROUP BY 1, 2 HAVING count(*) > 1) x
UNION ALL SELECT 'month_' || to_char(scan_date, 'YYYY-MM') || '_pairs/pass', count(*)::text || '/' || count(*) FILTER (WHERE any_pass)::text FROM pr GROUP BY to_char(scan_date, 'YYYY-MM')
UNION ALL SELECT 'era_' || CASE WHEN scan_date < DATE '2026-08-22' THEN 'A' ELSE 'B' END || '_pairs/pass', count(*)::text || '/' || count(*) FILTER (WHERE any_pass)::text FROM pr GROUP BY 1
UNION ALL SELECT 'block_' || CASE WHEN scan_date <= DATE '2026-08-14' THEN 'DISC' ELSE 'HELD' END || '_pairs/pass', count(*)::text || '/' || count(*) FILTER (WHERE any_pass)::text FROM pr GROUP BY 1
-- alerted subset
UNION ALL SELECT 'live_alert_pairs_0501_end', count(*)::text FROM al, endd WHERE alert_date BETWEEN DATE '2026-05-01' AND endd.e
UNION ALL SELECT 'live_alert_pairs_0501_0911', count(*)::text FROM al WHERE alert_date BETWEEN DATE '2026-05-01' AND DATE '2026-09-11'
UNION ALL SELECT 'live_alert_pairs_0501_0821', count(*)::text FROM al WHERE alert_date BETWEEN DATE '2026-05-01' AND DATE '2026-08-21'
UNION ALL SELECT 'live_alert_rows_dup_pairs', count(*)::text FROM al WHERE n_rows > 1
UNION ALL SELECT 'alerts_min_date_any_source', min(alert_date)::text FROM mi_ep_alerts
UNION ALL SELECT 'alerts_source_' || COALESCE(source, 'NULL'), count(*)::text FROM mi_ep_alerts WHERE alert_date BETWEEN DATE '2026-05-01' AND DATE '2026-09-11' GROUP BY source
UNION ALL SELECT 'pass_pairs_with_live_alert', count(*)::text FROM pr JOIN al ON al.ticker = pr.ticker AND al.alert_date = pr.scan_date WHERE pr.any_pass
UNION ALL SELECT 'pass_pairs_no_live_alert', count(*)::text FROM pr WHERE any_pass AND NOT EXISTS (SELECT 1 FROM al WHERE al.ticker = pr.ticker AND al.alert_date = pr.scan_date)
UNION ALL SELECT 'pass_pairs_no_live_alert_date_range', min(scan_date)::text || '..' || max(scan_date)::text FROM pr WHERE any_pass AND NOT EXISTS (SELECT 1 FROM al WHERE al.ticker = pr.ticker AND al.alert_date = pr.scan_date)
UNION ALL SELECT 'pass_pairs_no_live_alert_on_or_after_0511', count(*)::text FROM pr WHERE any_pass AND scan_date >= DATE '2026-05-11' AND NOT EXISTS (SELECT 1 FROM al WHERE al.ticker = pr.ticker AND al.alert_date = pr.scan_date)
UNION ALL SELECT 'nopass_pairs_with_live_alert:' || pr.ticker || '_' || pr.scan_date::text, to_char(al.first_created AT TIME ZONE 'America/New_York', 'HH24:MI') FROM pr JOIN al ON al.ticker = pr.ticker AND al.alert_date = pr.scan_date WHERE NOT pr.any_pass
UNION ALL SELECT 'live_alerts_in_window_with_no_scored_pair', count(*)::text FROM al, endd WHERE al.alert_date BETWEEN DATE '2026-05-01' AND endd.e AND NOT EXISTS (SELECT 1 FROM pr WHERE pr.ticker = al.ticker AND pr.scan_date = al.alert_date)
UNION ALL SELECT 'live_alerts_in_window_with_no_scored_pair:' || al.ticker || '_' || al.alert_date::text, (SELECT count(*)::text || ' scanlog rows any' FROM mi_ep_scan_log l WHERE l.ticker = al.ticker AND l.scan_date = al.alert_date) FROM al, endd WHERE al.alert_date BETWEEN DATE '2026-05-01' AND endd.e AND NOT EXISTS (SELECT 1 FROM pr WHERE pr.ticker = al.ticker AND pr.scan_date = al.alert_date)
-- scan-log coverage around the window start (is there an earlier gap / regime change?)
UNION ALL SELECT 'scanlog_scored_pairs_by_week_' || to_char(date_trunc('week', scan_date), 'YYYY-MM-DD'), count(DISTINCT (ticker, scan_date))::text FROM mi_ep_scan_log WHERE ep_score IS NOT NULL AND scan_date BETWEEN DATE '2026-04-13' AND DATE '2026-09-11' GROUP BY 1
UNION ALL SELECT 'scanlog_first_date', min(scan_date)::text FROM mi_ep_scan_log
-- price mix of the chosen population (independent of prev_close choice: use the lowest prev_close tick)
UNION ALL SELECT 'pairs_prevclose_lt5', count(*)::text FROM (SELECT ticker, scan_date, min(prev_close) pc FROM mi_ep_scan_log l, endd WHERE l.scan_date BETWEEN DATE '2026-05-01' AND endd.e AND l.ep_score IS NOT NULL GROUP BY 1, 2) x WHERE pc < 5
;
