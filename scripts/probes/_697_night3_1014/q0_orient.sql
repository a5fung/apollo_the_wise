-- READ-ONLY. Night 3 (2026-10-14) orientation: did the 17:25 ET scan run, how many rows/holds, bars present.
SET default_transaction_read_only = on;
SET statement_timeout = '30s';
\echo '== B. newest scan_dates in mi_flag_candidates (rows, raw TRIGGERED, holds, WATCH-or-better, written)'
SELECT scan_date, count(*) AS rows,
       count(*) FILTER (WHERE stage='TRIGGERED' AND held_from_stage IS NULL) AS raw_trig,
       count(*) FILTER (WHERE held_from_stage IS NOT NULL) AS holds,
       count(*) FILTER (WHERE stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED')) AS watch_or_better,
       to_char(max(created_at) AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS last_written_et
FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-09' GROUP BY scan_date ORDER BY scan_date;
\echo '== C. bars present for the newest days in mi_daily_closes'
SELECT trade_date, count(*) FROM mi_daily_closes WHERE trade_date >= DATE '2026-10-09' GROUP BY trade_date ORDER BY 1;
