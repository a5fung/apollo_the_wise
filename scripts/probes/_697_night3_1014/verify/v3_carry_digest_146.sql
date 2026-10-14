-- READ-ONLY. VERIFIER. (1) carry re-derived with a DIFFERENT session source: market sessions = mi_daily_closes trade_dates
-- with >= 5000 bars (not the scan dates of mi_flag_candidates), 25-session long window, 5-session short window, bar on D required,
-- >= 60 bars; compared name-by-name to the 10-14 tags. (2) digest rows vs board. (3) #146 raw TRIGGERED / stamps.
SET default_transaction_read_only = on;
SET statement_timeout = '90s';
\echo '== V3a. the 26 market sessions before 10-14 per mi_daily_closes (lag, date, bars)'
SELECT ROW_NUMBER() OVER (ORDER BY trade_date DESC) lag, trade_date, n FROM (
  SELECT trade_date, count(*) n FROM mi_daily_closes WHERE trade_date < DATE '2026-10-14' AND trade_date >= DATE '2026-08-15'
  GROUP BY 1 HAVING count(*) >= 5000) s ORDER BY trade_date DESC LIMIT 26;
\echo '== V3b. name-by-name: expected tag (bar-session def) vs actual 10-14 tag; only rows where they differ or a carry tag exists'
WITH ms AS (
  SELECT trade_date, ROW_NUMBER() OVER (ORDER BY trade_date DESC) lag FROM (
    SELECT trade_date FROM mi_daily_closes WHERE trade_date < DATE '2026-10-14' AND trade_date >= DATE '2026-08-15'
    GROUP BY 1 HAVING count(*) >= 5000) s
), st AS (
  SELECT c.ticker, c.stage, ms.lag FROM mi_flag_candidates c JOIN ms ON ms.trade_date = c.scan_date
  WHERE ms.lag <= 25 AND c.stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED')
), bar AS (
  SELECT ticker FROM mi_daily_closes WHERE trade_date = DATE '2026-10-14'
), exp AS (
  SELECT ticker,
    CASE WHEN bool_or(lag <= 5) THEN 'flag_stage_carryforward'
         WHEN bool_or(stage <> 'WATCH') THEN 'flag_pivot_window_carryforward' END AS exp_tag,
    min(lag) min_lag, string_agg(DISTINCT stage, ',') stages_seen
  FROM st WHERE ticker IN (SELECT ticker FROM bar) GROUP BY ticker
), act AS (
  SELECT ticker, stage, universe_sources us,
    CASE WHEN universe_sources @> ARRAY['flag_stage_carryforward'] THEN 'flag_stage_carryforward'
         WHEN universe_sources @> ARRAY['flag_pivot_window_carryforward'] THEN 'flag_pivot_window_carryforward' END AS act_tag
  FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-14'
)
SELECT COALESCE(e.ticker, a.ticker) ticker, e.exp_tag, a.act_tag, e.min_lag, e.stages_seen, a.stage stage_1014, a.us,
       (SELECT count(*) FROM mi_daily_closes d WHERE d.ticker = COALESCE(e.ticker, a.ticker) AND d.trade_date <= DATE '2026-10-14') bars,
       CASE WHEN a.ticker IS NULL THEN 'NO_ROW' WHEN e.exp_tag IS NOT DISTINCT FROM a.act_tag THEN 'ok' ELSE 'DIFF' END verdict
FROM exp e FULL JOIN act a ON a.ticker = e.ticker
WHERE e.exp_tag IS NOT NULL OR a.act_tag IS NOT NULL
ORDER BY verdict, e.exp_tag, 1;
\echo '== V3c. carry-only rows on 10-14 (carry tag, no organic/R3/9M tag): count by tag x stage'
SELECT CASE WHEN universe_sources @> ARRAY['flag_stage_carryforward'] THEN 'short' ELSE 'long' END tag, stage, count(*)
FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-14'
  AND universe_sources && ARRAY['flag_stage_carryforward','flag_pivot_window_carryforward']
  AND NOT universe_sources && ARRAY['rs_top200','rs_1m_80','momentum_25pct','magna53_failed_r3','ninem_universe_watch']
GROUP BY 1,2 ORDER BY 1,2;
\echo '== V3d. long-tag rows per scan date since 09-29 (the OLD code never wrote this tag)'
SELECT scan_date, count(*) FILTER (WHERE universe_sources @> ARRAY['flag_pivot_window_carryforward']) long_tag,
       count(*) FILTER (WHERE universe_sources @> ARRAY['flag_stage_carryforward']) short_tag
FROM mi_flag_candidates WHERE scan_date >= DATE '2026-09-29' GROUP BY 1 ORDER BY 1;
\echo '== V3e. WATCH names stored in the last 5 sessions with NO organic/R3/9M tag on 10-14 (the DoD clause): their 10-14 row'
SELECT c.ticker, max(c.scan_date) last_watch, t.stage stage_1014, t.universe_sources
FROM mi_flag_candidates c LEFT JOIN mi_flag_candidates t ON t.ticker = c.ticker AND t.scan_date = DATE '2026-10-14'
WHERE c.scan_date IN (DATE '2026-10-07', DATE '2026-10-08', DATE '2026-10-09', DATE '2026-10-12', DATE '2026-10-13') AND c.stage = 'WATCH'
  AND (t.ticker IS NULL OR NOT t.universe_sources && ARRAY['rs_top200','rs_1m_80','momentum_25pct','magna53_failed_r3','ninem_universe_watch'])
GROUP BY c.ticker, t.stage, t.universe_sources ORDER BY 1;
\echo '== V3f. flag_digest_sent rows since 10-09 (ET time, detail) and the board (stored COILED/TRIGGERED/TIGHTENING) that scan date'
SELECT a.id, to_char(a.created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, a.detail,
       (SELECT string_agg(ticker||':'||stage, ',' ORDER BY ticker) FROM mi_flag_candidates c WHERE c.scan_date = (a.created_at AT TIME ZONE 'America/New_York')::date AND c.stage IN ('TIGHTENING','COILED','TRIGGERED')) board
FROM mi_audit_log a WHERE a.event_type = 'flag_digest_sent' ORDER BY a.id;
\echo '== V3g. per scan date since 10-09: board TIGHTENING+ names and digest rows that ET day'
SELECT c.scan_date, count(*) FILTER (WHERE c.stage IN ('TIGHTENING','COILED','TRIGGERED')) board_tight_plus,
  (SELECT count(*) FROM mi_audit_log a WHERE a.event_type='flag_digest_sent' AND (a.created_at AT TIME ZONE 'America/New_York')::date = c.scan_date) digest_rows
FROM mi_flag_candidates c WHERE c.scan_date >= DATE '2026-10-09' GROUP BY 1 ORDER BY 1;
\echo '== V3h. #146: any TRIGGERED row (raw or held) or any triggered_from stamp 10-12..10-14'
SELECT scan_date, ticker, stage, held_from_stage, triggered_from FROM mi_flag_candidates
WHERE scan_date BETWEEN DATE '2026-10-12' AND DATE '2026-10-14' AND (stage='TRIGGERED' OR held_from_stage='TRIGGERED' OR triggered_from IS NOT NULL);
\echo '== V3i. flag-related audit event types in the last 3 ET days (errors? failures?)'
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-10-12 00:00-04' AND (event_type ILIKE '%flag%' OR summary ILIKE '%flag_scan%') GROUP BY 1 ORDER BY 1;
