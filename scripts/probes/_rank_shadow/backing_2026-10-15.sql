\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
SELECT 'B1_alert_vs_shadow' AS chk, count(*) AS live_alert_rows, count(DISTINCT alert_date) AS live_alert_days, max(alert_date) AS latest_alert,
  count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM mi_alert_rank_shadow s WHERE s.ticker=a.ticker AND s.alert_date=a.alert_date)) AS alerts_without_shadow,
  (SELECT count(*) FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16') AS shadow_rows
FROM mi_ep_alerts a WHERE a.alert_date > DATE '2026-08-16' AND a.source='live';
SELECT 'B2_scan_filter_by_day' AS chk, alert_date, source, count(*) FROM mi_ep_missed_outcomes WHERE alert_date >= DATE '2026-10-09' GROUP BY 2,3 ORDER BY 2,3;
SELECT 'B3_ep_alert_events' AS chk, (created_at AT TIME ZONE 'America/New_York')::date AS d, count(*) FROM mi_audit_log WHERE event_type='ep_alert' AND created_at >= TIMESTAMPTZ '2026-10-05 00:00-04' GROUP BY 2 ORDER BY 2;
SELECT 'B4_orb_window_jobs' AS chk, job_id, status, count(*), min(started_at AT TIME ZONE 'America/New_York') AS first_et, max(started_at AT TIME ZONE 'America/New_York') AS last_et FROM mi_job_runs WHERE started_at >= TIMESTAMPTZ '2026-10-15 09:25-04' AND started_at < TIMESTAMPTZ '2026-10-15 10:10-04' AND job_id ILIKE 'ep_scan%' GROUP BY 2,3 ORDER BY 2,3;
