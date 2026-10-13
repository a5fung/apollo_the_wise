\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
SELECT '1_job_runs' AS chk, job_id, status, rows_written, scheduled_for AT TIME ZONE 'America/New_York' AS sched_et, finished_at AT TIME ZONE 'America/New_York' AS fin_et, left(coalesce(error_message,''),80) AS err FROM mi_job_runs WHERE job_id='alert_rank_shadow' ORDER BY id DESC LIMIT 4;
SELECT '2_predicate_n_sessions' AS chk, count(DISTINCT alert_date) AS n_sessions, count(*) AS n_rows, max(alert_date) AS latest FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16';
SELECT '3_shadow_rows_1013' AS chk, ticker, alert_date, score_tier, trade_filled, composite_rank_eod, pool_size_eod FROM mi_alert_rank_shadow WHERE alert_date >= DATE '2026-10-09' ORDER BY alert_date, ticker;
SELECT '4_daily_closes_latest' AS chk, max(trade_date) AS latest_close, count(*) FILTER (WHERE trade_date=DATE '2026-10-13') AS rows_1013 FROM mi_daily_closes;
SELECT '5_close_1013_for_pools' AS chk, ticker, trade_date, close_price FROM mi_daily_closes WHERE trade_date=DATE '2026-10-13' AND ticker IN ('ITUB','NU','PBR','CEG','TLN','VST','PENG','WOLF');
