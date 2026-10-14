-- READ-ONLY. VERIFIER (independent of the checker). Population of the 10-12..10-14 scans:
-- one write batch per night at ~17:25 ET, no duplicate ticker rows, no stray/rehearsal writes, columns present.
SET default_transaction_read_only = on;
SET statement_timeout = '60s';
\echo '== V1a. mi_flag_candidates columns (is there an updated_at that a rerun would bump?)'
SELECT column_name FROM information_schema.columns WHERE table_name='mi_flag_candidates' AND column_name IN ('created_at','updated_at','held_from_stage','triggered_from','universe_sources') ORDER BY 1;
\echo '== V1b. per scan_date: rows, distinct tickers, write window ET, rows written outside 17:20-17:40 ET of that date'
SELECT scan_date, count(*) rows, count(DISTINCT ticker) tickers,
       to_char(min(created_at AT TIME ZONE 'America/New_York'),'MM-DD HH24:MI:SS') first_et,
       to_char(max(created_at AT TIME ZONE 'America/New_York'),'MM-DD HH24:MI:SS') last_et,
       count(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York') NOT BETWEEN scan_date + time '17:20' AND scan_date + time '17:40') AS outside_window,
       count(*) FILTER (WHERE held_from_stage IS NOT NULL) holds,
       count(*) FILTER (WHERE stage='TRIGGERED' AND held_from_stage IS NULL) raw_triggered,
       count(*) FILTER (WHERE triggered_from IS NOT NULL) stamped,
       count(*) FILTER (WHERE stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED')) watch_plus
FROM mi_flag_candidates WHERE scan_date BETWEEN DATE '2026-10-09' AND DATE '2026-10-15' GROUP BY 1 ORDER BY 1;
\echo '== V1c. stage mix 10-14 (stored stage; raw = coalesce(held_from_stage, stage))'
SELECT stage, coalesce(held_from_stage, stage) raw, count(*) FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-14' GROUP BY 1,2 ORDER BY 1,2;
\echo '== V1d. every 10-14 row whose universe_sources is empty/NULL (would mean an unexplained admission)'
SELECT count(*) FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-14' AND (universe_sources IS NULL OR cardinality(universe_sources)=0);
