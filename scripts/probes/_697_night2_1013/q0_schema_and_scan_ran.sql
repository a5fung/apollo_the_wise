-- READ-ONLY. Orientation: job-runs columns, did tonight's 17:25 ET flag scan run, what is the newest scan_date.
SET default_transaction_read_only = on;
SET statement_timeout = '30s';
\echo '== A. mi_job_runs columns'
SELECT column_name FROM information_schema.columns WHERE table_name='mi_job_runs' ORDER BY ordinal_position;
\echo '== B. newest scan_dates in mi_flag_candidates (rows, raw TRIGGERED, holds)'
SELECT scan_date, count(*) AS rows,
       count(*) FILTER (WHERE stage='TRIGGERED' AND held_from_stage IS NULL) AS raw_trig,
       count(*) FILTER (WHERE held_from_stage IS NOT NULL) AS holds,
       count(*) FILTER (WHERE stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED')) AS watch_or_better,
       max(created_at) AS last_written
FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-09' GROUP BY scan_date ORDER BY scan_date;
\echo '== C. bars present for 10-13 in mi_daily_closes'
SELECT trade_date, count(*) FROM mi_daily_closes WHERE trade_date >= DATE '2026-10-09' GROUP BY trade_date ORDER BY 1;
