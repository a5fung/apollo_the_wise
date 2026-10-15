-- READ-ONLY. #697 night 4 (10-15): did the 10-15 scan run, what did it write.
SET default_transaction_read_only = on;
SET statement_timeout = '60s';
\echo '== A. newest scan_dates in mi_flag_candidates (rows, raw TRIGGERED, holds, WATCH-or-better, written)'
SELECT scan_date, count(*) rows, count(*) FILTER (WHERE stage='TRIGGERED') raw_trig,
       count(*) FILTER (WHERE held_from_stage IS NOT NULL) holds,
       count(*) FILTER (WHERE stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED')) watch_or_better,
       to_char(max(created_at) AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') last_written_et
FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-09' GROUP BY 1 ORDER BY 1;
\echo '== B. bars in mi_daily_closes for the newest days'
SELECT trade_date, count(*) FROM mi_daily_closes WHERE trade_date >= DATE '2026-10-12' GROUP BY 1 ORDER BY 1;
\echo '== C. stage mix on 10-15 (with holds)'
SELECT stage, count(*), count(*) FILTER (WHERE held_from_stage IS NOT NULL) holds
FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-15' GROUP BY 1 ORDER BY 1;
\echo '== D. every WATCH-or-better row on 10-15'
SELECT ticker, stage, held_from_stage, reason, universe_sources
FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-15' AND stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED') ORDER BY stage, ticker;
