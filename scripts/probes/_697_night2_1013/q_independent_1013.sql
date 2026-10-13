-- READ-ONLY. Independent re-derivation of the carry set for D = 2026-10-12 (not the shipped SQL).
SET default_transaction_read_only = on;
SET statement_timeout = '60s';
\echo '== 1. scan sessions before D (lag, date, rows, stages)'
SELECT ROW_NUMBER() OVER (ORDER BY s.scan_date DESC) AS lag, s.scan_date, s.n
FROM (SELECT scan_date, count(*) n FROM mi_flag_candidates
      WHERE scan_date < DATE '2026-10-13' AND scan_date >= DATE '2026-10-13' - 60
        AND EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = mi_flag_candidates.scan_date)
      GROUP BY scan_date) s
ORDER BY s.scan_date DESC LIMIT 8;

\echo '== 2. expected carry set vs what was written on D (every expected name must have a row on D)'
WITH sd AS (
  SELECT s.scan_date, ROW_NUMBER() OVER (ORDER BY s.scan_date DESC) AS lag
  FROM (SELECT DISTINCT scan_date FROM mi_flag_candidates
        WHERE scan_date < DATE '2026-10-13' AND scan_date >= DATE '2026-10-13' - 60) s
  WHERE EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = s.scan_date)
), st AS (
  SELECT c.ticker, c.stage, sd.lag, c.scan_date
  FROM mi_flag_candidates c JOIN sd ON sd.scan_date = c.scan_date
  WHERE sd.lag <= 25 AND c.stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED')
    AND EXISTS (SELECT 1 FROM mi_daily_closes dc WHERE dc.ticker=c.ticker AND dc.trade_date = DATE '2026-10-13')
), exp AS (
  SELECT ticker,
         bool_or(lag <= 5) AS short_win,
         bool_or(stage IN ('TIGHTENING','COILED','TRIGGERED') AND lag <= 25) AS long_win,
         min(lag) AS min_lag,
         (array_agg(stage ORDER BY lag))[1] AS latest_stored_stage,
         (array_agg(scan_date ORDER BY lag))[1] AS latest_stored_date
  FROM st GROUP BY ticker
), exp2 AS (
  SELECT ticker, latest_stored_stage, latest_stored_date, min_lag,
         CASE WHEN short_win THEN 'short' WHEN long_win THEN 'long' END AS expect_tag
  FROM exp
  -- short window needs WATCH-or-better in lag<=5; recompute precisely:
), exp3 AS (
  SELECT e.ticker, e.latest_stored_stage, e.latest_stored_date,
         CASE WHEN EXISTS (SELECT 1 FROM st x WHERE x.ticker=e.ticker AND x.lag<=5) THEN 'short'
              WHEN EXISTS (SELECT 1 FROM st x WHERE x.ticker=e.ticker AND x.lag<=25 AND x.stage IN ('TIGHTENING','COILED','TRIGGERED')) THEN 'long'
         END AS expect_tag
  FROM exp e
), t AS (
  SELECT ticker, stage, universe_sources AS us FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-13'
)
SELECT e.expect_tag,
       count(*) AS expected_names,
       count(t.ticker) AS have_row_on_d,
       count(*) FILTER (WHERE t.ticker IS NULL) AS missing_row,
       count(*) FILTER (WHERE e.expect_tag='short' AND t.us @> ARRAY['flag_stage_carryforward']::text[]) AS tagged_short,
       count(*) FILTER (WHERE e.expect_tag='long'  AND t.us @> ARRAY['flag_pivot_window_carryforward']::text[]) AS tagged_long,
       count(*) FILTER (WHERE t.ticker IS NOT NULL AND ((e.expect_tag='short' AND NOT t.us @> ARRAY['flag_stage_carryforward']::text[]) OR (e.expect_tag='long' AND NOT t.us @> ARRAY['flag_pivot_window_carryforward']::text[]))) AS wrong_tag
FROM exp3 e LEFT JOIN t ON t.ticker=e.ticker
WHERE e.expect_tag IS NOT NULL
GROUP BY e.expect_tag ORDER BY 1;

\echo '== 2b. rows on D carrying a carry tag that the independent derivation does NOT expect (should be 0)'
WITH sd AS (
  SELECT s.scan_date, ROW_NUMBER() OVER (ORDER BY s.scan_date DESC) AS lag
  FROM (SELECT DISTINCT scan_date FROM mi_flag_candidates
        WHERE scan_date < DATE '2026-10-13' AND scan_date >= DATE '2026-10-13' - 60) s
  WHERE EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = s.scan_date)
), st AS (
  SELECT c.ticker, c.stage, sd.lag FROM mi_flag_candidates c JOIN sd ON sd.scan_date=c.scan_date
  WHERE sd.lag <= 25 AND c.stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED')
)
SELECT t.ticker, t.stage, t.universe_sources
FROM mi_flag_candidates t
WHERE t.scan_date = DATE '2026-10-13'
  AND (t.universe_sources && ARRAY['flag_stage_carryforward','flag_pivot_window_carryforward']::text[])
  AND NOT EXISTS (SELECT 1 FROM st WHERE st.ticker=t.ticker AND ((st.lag<=5) OR (st.lag<=25 AND st.stage IN ('TIGHTENING','COILED','TRIGGERED'))));

\echo '== 3. the 10 long-tag rows on D (ticker, stage today, organic tags)'
SELECT ticker, stage, universe_sources, base_age, failed_at, reason
FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-13' AND universe_sources @> ARRAY['flag_pivot_window_carryforward']::text[]
ORDER BY stage, ticker;

\echo '== 4. carry-only rows on D by stored latest stage (who is only here because of the carry)'
SELECT t.ticker, t.stage AS stage_today, t.universe_sources
FROM mi_flag_candidates t
WHERE t.scan_date = DATE '2026-10-13'
  AND t.universe_sources && ARRAY['flag_stage_carryforward','flag_pivot_window_carryforward']::text[]
  AND NOT t.universe_sources && ARRAY['rs_top200','rs_1m_80','momentum_25pct','magna53_failed_r3','ninem_universe_watch']::text[]
ORDER BY t.stage, t.ticker;

\echo '== 5. stage mix on D'
SELECT stage, count(*) , count(*) FILTER (WHERE held_from_stage IS NOT NULL) AS holds FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-13' GROUP BY stage ORDER BY 1;

\echo '== 6. the hold history: every row with held_from_stage in the last 3 sessions (10-08..10-12)'
SELECT ticker, scan_date, stage, held_from_stage FROM mi_flag_candidates WHERE held_from_stage IS NOT NULL AND scan_date >= DATE '2026-10-08' ORDER BY scan_date, ticker;

\echo '== 7. fingerprint row(s): ticker with a hold on its prior row and a fallen stage on D'
SELECT t.ticker, p.scan_date AS prior_date, p.stage AS prior_stage, p.held_from_stage AS prior_held_from, t.stage AS stage_d, t.held_from_stage AS held_d
FROM mi_flag_candidates t
JOIN LATERAL (SELECT * FROM mi_flag_candidates x WHERE x.ticker=t.ticker AND x.scan_date < t.scan_date AND x.scan_date >= t.scan_date - 5 ORDER BY x.scan_date DESC LIMIT 1) p ON true
WHERE t.scan_date = DATE '2026-10-13' AND p.held_from_stage IS NOT NULL;

\echo '== 8. audit rows since 2026-10-12 00:00 PT for flag digest / transitions / errors'
SELECT created_at, event_type, left(summary,120) summary FROM mi_audit_log
WHERE created_at >= TIMESTAMPTZ '2026-10-12 00:00-07' AND (event_type ILIKE '%flag%' OR event_type ILIKE '%digest%')
ORDER BY created_at;

\echo '== 8b. any flag_digest_sent ever (to show the event type exists/works on any prior digest)'
SELECT count(*) n, min(created_at) first_at, max(created_at) last_at FROM mi_audit_log WHERE event_type='flag_digest_sent';

\echo '== 9. stored WATCH-or-better names in the last 5 sessions that have NO bar on D (excused by design) and with <60 bars'
WITH sd AS (
  SELECT s.scan_date, ROW_NUMBER() OVER (ORDER BY s.scan_date DESC) AS lag
  FROM (SELECT DISTINCT scan_date FROM mi_flag_candidates WHERE scan_date < DATE '2026-10-13' AND scan_date >= DATE '2026-10-13' - 60) s
  WHERE EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = s.scan_date)
)
SELECT count(DISTINCT c.ticker) AS stored_watch_plus_names_last5,
       count(DISTINCT c.ticker) FILTER (WHERE EXISTS (SELECT 1 FROM mi_daily_closes dc WHERE dc.ticker=c.ticker AND dc.trade_date=DATE '2026-10-13')) AS with_bar_on_d,
       count(DISTINCT c.ticker) FILTER (WHERE EXISTS (SELECT 1 FROM mi_flag_candidates t WHERE t.ticker=c.ticker AND t.scan_date=DATE '2026-10-13')) AS with_row_on_d
FROM mi_flag_candidates c JOIN sd ON sd.scan_date=c.scan_date
WHERE sd.lag <= 5 AND c.stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED');
