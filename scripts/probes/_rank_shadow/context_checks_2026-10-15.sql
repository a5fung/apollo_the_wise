\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
SELECT '1_job_runs' AS chk, job_id, status, rows_written, started_at AT TIME ZONE 'America/New_York' AS start_et, finished_at AT TIME ZONE 'America/New_York' AS fin_et, left(coalesce(error_message,''),80) AS err FROM mi_job_runs WHERE job_id='alert_rank_shadow' ORDER BY id DESC LIMIT 5;
SELECT '2_predicate_n_sessions' AS chk, count(DISTINCT alert_date) AS n_sessions, count(*) AS n_rows, max(alert_date) AS latest FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16';
SELECT '3_shadow_rows_since_1009' AS chk, ticker, alert_date, score_tier, trade_filled, composite_rank_eod, pool_size_eod FROM mi_alert_rank_shadow WHERE alert_date >= DATE '2026-10-09' ORDER BY alert_date, ticker;
SELECT '4_daily_closes_latest' AS chk, max(trade_date) AS latest_close, count(*) FILTER (WHERE trade_date=DATE '2026-10-15') AS rows_1015 FROM mi_daily_closes;
SELECT '5_closes_per_day' AS chk, trade_date, count(*) FROM mi_daily_closes WHERE trade_date >= DATE '2026-10-09' GROUP BY trade_date ORDER BY trade_date;
SELECT '6_ep_alerts_by_date_source' AS chk, alert_date, source, count(*) AS n_alerts, count(*) FILTER (WHERE score_tier='HIGH') AS n_high FROM mi_ep_alerts WHERE alert_date >= DATE '2026-10-09' GROUP BY alert_date, source ORDER BY alert_date, source;
SELECT '7_audit_rank' AS chk, event_type, left(summary,140) AS summary, created_at AT TIME ZONE 'America/New_York' AS at_et FROM mi_audit_log WHERE event_type ILIKE '%rank_shadow%' ORDER BY created_at DESC LIMIT 4;
SELECT '8_wolf_sessions' AS chk, trade_date, open_price, high_price, low_price FROM mi_daily_closes WHERE ticker='WOLF' AND trade_date >= DATE '2026-10-08' ORDER BY trade_date;
SELECT '9_alerts_1015_any_source' AS chk, id, ticker, alert_date, source, score_tier, ep_score, created_at AT TIME ZONE 'America/New_York' AS created_et FROM mi_ep_alerts WHERE alert_date >= DATE '2026-10-15' ORDER BY id;
SELECT '10_scan_jobs_today' AS chk, job_id, status, count(*), max(finished_at AT TIME ZONE 'America/New_York') AS last_fin_et FROM mi_job_runs WHERE scheduled_for >= TIMESTAMPTZ '2026-10-15 00:00-04' AND (job_id ILIKE '%ep%' OR job_id ILIKE '%orb%' OR job_id ILIKE '%scan%') GROUP BY 2,3 ORDER BY 2,3;
