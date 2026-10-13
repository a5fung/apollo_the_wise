-- READ-ONLY. Verifier re-derivation of #697 night 2 (scan_date 2026-10-13), independent of the checker's SQL.
SET default_transaction_read_only = on;
SET statement_timeout = '60s';
\echo '== P1. population: rows / distinct tickers / write window (ET) per scan_date >= 10-09, and any scan_date > 10-13'
SELECT scan_date, count(*) n, count(DISTINCT ticker) tickers,
       min(created_at AT TIME ZONE 'America/New_York') first_et, max(created_at AT TIME ZONE 'America/New_York') last_et,
       count(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::time NOT BETWEEN '17:20' AND '17:40') off_window
FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-09' GROUP BY scan_date ORDER BY scan_date;
\echo '== P2. job runs for flag jobs since 10-12 (ET)'
SELECT job_id, scheduled_for AT TIME ZONE 'America/New_York' sched_et, started_at AT TIME ZONE 'America/New_York' start_et,
       status, rows_written, error_message
FROM mi_job_runs WHERE started_at >= TIMESTAMPTZ '2026-10-12 00:00-04' AND job_id ILIKE '%flag%' ORDER BY started_at;
\echo '== P3. every universe_sources tag on 10-13 (is the organic list complete?)'
SELECT tag, count(*) FROM mi_flag_candidates, unnest(universe_sources) tag WHERE scan_date = DATE '2026-10-13' GROUP BY tag ORDER BY 2 DESC;
\echo '== C1. carry rows on 10-12 and 10-13: long tag, short tag, carry-only (no tag outside the two carry tags)'
SELECT scan_date,
  count(*) FILTER (WHERE 'flag_pivot_window_carryforward' = ANY(universe_sources)) long_tag,
  count(*) FILTER (WHERE 'flag_stage_carryforward' = ANY(universe_sources)) short_tag,
  count(*) FILTER (WHERE universe_sources <@ ARRAY['flag_stage_carryforward','flag_pivot_window_carryforward']::text[]
                     AND cardinality(universe_sources) > 0) carry_only
FROM mi_flag_candidates WHERE scan_date IN (DATE '2026-10-09', DATE '2026-10-12', DATE '2026-10-13') GROUP BY scan_date ORDER BY 1;
\echo '== C2. last 5 scan sessions before 10-13 (by distinct scan_date)'
SELECT DISTINCT scan_date FROM mi_flag_candidates WHERE scan_date < DATE '2026-10-13' ORDER BY scan_date DESC LIMIT 5;
\echo '== C3. stored WATCH-or-better names in those 5 sessions: row on 10-13? bar on 10-13? bars to date'
WITH s5 AS (SELECT DISTINCT scan_date FROM mi_flag_candidates WHERE scan_date < DATE '2026-10-13' ORDER BY scan_date DESC LIMIT 5),
names AS (SELECT c.ticker, max(c.scan_date) last_seen, string_agg(c.stage || '@' || to_char(c.scan_date,'MM-DD'), ',' ORDER BY c.scan_date) hist
          FROM mi_flag_candidates c JOIN s5 USING (scan_date) WHERE c.stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED') GROUP BY c.ticker)
SELECT n.ticker, n.hist,
       t.stage AS stage_1013, t.universe_sources,
       EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.ticker = n.ticker AND d.trade_date = DATE '2026-10-13') bar_1013
FROM names n LEFT JOIN mi_flag_candidates t ON t.ticker = n.ticker AND t.scan_date = DATE '2026-10-13' ORDER BY n.ticker;
\echo '== C4. TIGHTENING-or-better names in the last 25 scan sessions before 10-13 with a bar on 10-13 and NO row on 10-13 (must be empty)'
WITH s25 AS (SELECT DISTINCT scan_date FROM mi_flag_candidates WHERE scan_date < DATE '2026-10-13' ORDER BY scan_date DESC LIMIT 25),
names AS (SELECT DISTINCT c.ticker FROM mi_flag_candidates c JOIN s25 USING (scan_date) WHERE c.stage IN ('TIGHTENING','COILED','TRIGGERED'))
SELECT n.ticker,
       EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.ticker = n.ticker AND d.trade_date = DATE '2026-10-13') bar_1013,
       EXISTS (SELECT 1 FROM mi_flag_candidates t WHERE t.ticker = n.ticker AND t.scan_date = DATE '2026-10-13') row_1013
FROM names n ORDER BY 1;
\echo '== H1. hold: per row on 10-12/10-13, yesterday = latest prior row within 5 calendar days (the code''s definition)'
WITH y AS (
  SELECT t.scan_date, t.ticker, t.stage, t.held_from_stage, p.stage pstage, p.held_from_stage pheld
  FROM mi_flag_candidates t
  LEFT JOIN LATERAL (SELECT stage, held_from_stage FROM mi_flag_candidates q
                     WHERE q.ticker = t.ticker AND q.scan_date < t.scan_date AND q.scan_date >= t.scan_date - 5
                     ORDER BY q.scan_date DESC LIMIT 1) p ON true
  WHERE t.scan_date IN (DATE '2026-10-12', DATE '2026-10-13'))
SELECT scan_date,
  count(*) FILTER (WHERE held_from_stage IS NOT NULL) holds_written,
  count(*) FILTER (WHERE held_from_stage IS NOT NULL AND pheld IS NOT NULL) violators,
  count(*) FILTER (WHERE pheld IS NOT NULL) yesterday_was_hold,
  count(*) FILTER (WHERE pheld IS NULL AND pstage IN ('TIGHTENING','COILED','TRIGGERED')) at_risk_first_hold,
  count(*) FILTER (WHERE pheld IS NULL AND pstage IN ('TIGHTENING','COILED','TRIGGERED')
                     AND CASE stage WHEN 'WATCH' THEN 1 WHEN 'TIGHTENING' THEN 2 WHEN 'COILED' THEN 3 WHEN 'TRIGGERED' THEN 4 ELSE 0 END
                       < CASE pstage WHEN 'WATCH' THEN 1 WHEN 'TIGHTENING' THEN 2 WHEN 'COILED' THEN 3 WHEN 'TRIGGERED' THEN 4 ELSE 0 END) at_risk_and_fell
FROM y GROUP BY scan_date ORDER BY 1;
\echo '== H2. holds_carried the 10-13 scan should log: tickers whose latest prior row in [10-08,10-12] is a hold'
SELECT count(*) FILTER (WHERE held_from_stage IS NOT NULL) expected_holds_carried_1013 FROM (
  SELECT DISTINCT ON (ticker) ticker, held_from_stage FROM mi_flag_candidates
  WHERE scan_date < DATE '2026-10-13' AND scan_date >= DATE '2026-10-13' - 5 ORDER BY ticker, scan_date DESC) z;
\echo '== H3. every hold row ever since 10-01 (old vs new code)'
SELECT scan_date, ticker, stage, held_from_stage FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-01' AND held_from_stage IS NOT NULL ORDER BY 1,2;
\echo '== D1. flag digest / transition / held / error audit rows since 10-12 00:00 ET'
SELECT id, created_at AT TIME ZONE 'America/New_York' t_et, event_type, summary, left(detail, 300) detail
FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-10-12 00:00-04'
  AND (event_type ILIKE 'flag%' OR summary ILIKE '%flag digest%') ORDER BY id;
\echo '== D2. flag_digest_sent / _error ever'
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York'), max(created_at AT TIME ZONE 'America/New_York')
FROM mi_audit_log WHERE event_type IN ('flag_digest_sent','flag_digest_sent_error') GROUP BY 1;
\echo '== D3. board on 10-13 at COILED/TRIGGERED (digest must not be quiet)'
SELECT ticker, stage, held_from_stage, triggered_from FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-13' AND stage IN ('TIGHTENING','COILED','TRIGGERED') ORDER BY 1;
\echo '== T1. #146: TRIGGERED rows and triggered_from stamps since 10-12'
SELECT scan_date, count(*) FILTER (WHERE stage = 'TRIGGERED') trig, count(*) FILTER (WHERE triggered_from IS NOT NULL) stamped
FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-12' GROUP BY 1 ORDER BY 1;
