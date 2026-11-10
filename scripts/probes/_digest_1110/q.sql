SET default_transaction_read_only = on;
SELECT count(*) AS rows, count(days_since_prior_alert) AS populated,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM mi_ep_alerts e WHERE e.ticker = s.ticker AND e.alert_date < s.scan_date AND e.alert_date >= s.scan_date - 60)) AS had_prior_alert_60d,
  min(scan_date), max(scan_date)
FROM mi_lowcap_lane_signals s;
SELECT job_id, started_at AT TIME ZONE 'America/New_York' AS et, status, rows_written, expected_min_rows FROM mi_job_runs WHERE job_id = 'breadth_live_refresh' ORDER BY started_at DESC LIMIT 6;
SELECT count(*) FILTER (WHERE rows_written = 0) zero, count(*) total, min(started_at AT TIME ZONE 'America/New_York')::date first_day FROM mi_job_runs WHERE job_id='breadth_live_refresh';
SELECT max(created_at) AT TIME ZONE 'America/New_York' AS last_row, count(*) FROM mi_flag_undercut_rally;
