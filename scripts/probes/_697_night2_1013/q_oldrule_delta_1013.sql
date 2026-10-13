-- READ-ONLY. What would the OLD carry rule (COILED/TIGHTENING only, previous 5 CALENDAR days) have admitted on 2026-10-12?
SET default_transaction_read_only = on;
SET statement_timeout = '60s';
\echo '== 1. old-rule admitted set vs new-rule tagged set on D'
WITH old AS (
  SELECT DISTINCT ticker FROM mi_flag_candidates
  WHERE scan_date < DATE '2026-10-13' AND scan_date >= DATE '2026-10-13' - 5 AND stage IN ('COILED','TIGHTENING')
    AND EXISTS (SELECT 1 FROM mi_daily_closes dc WHERE dc.ticker=mi_flag_candidates.ticker AND dc.trade_date=DATE '2026-10-13')
), t AS (
  SELECT ticker, universe_sources us FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-13'
  AND universe_sources && ARRAY['flag_stage_carryforward','flag_pivot_window_carryforward']::text[]
)
SELECT (SELECT count(*) FROM old) AS old_rule_names,
       (SELECT count(*) FROM t) AS new_rule_names,
       (SELECT count(*) FROM t WHERE ticker NOT IN (SELECT ticker FROM old)) AS only_new_rule,
       (SELECT count(*) FROM t WHERE ticker NOT IN (SELECT ticker FROM old) AND NOT us && ARRAY['rs_top200','rs_1m_80','momentum_25pct','magna53_failed_r3','ninem_universe_watch']::text[]) AS only_new_rule_and_carry_only;
\echo '== 2. stored TRIGGERED rows in the last 25 scan dates (is the stored-TRIGGERED carry branch exercised?)'
SELECT ticker, scan_date, stage, held_from_stage, triggered_from FROM mi_flag_candidates
WHERE stage='TRIGGERED' AND scan_date >= DATE '2026-09-08' AND scan_date < DATE '2026-10-13' ORDER BY scan_date, ticker;
\echo '== 3. KOD last 6 rows'
SELECT scan_date, stage, held_from_stage, left(reason,80) reason, universe_sources FROM mi_flag_candidates WHERE ticker='KOD' AND scan_date >= DATE '2026-10-05' ORDER BY scan_date;
\echo '== 4. TIGHTENING/COILED rows on 10-08/10-09 (what the board held going into tonight)'
SELECT scan_date, stage, count(*) FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-05' AND stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED') GROUP BY 1,2 ORDER BY 1,2;
