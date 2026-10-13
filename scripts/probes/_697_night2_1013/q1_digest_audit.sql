-- READ-ONLY. Digest/transition audit trail for the two nights since the 10-11 deploy, plus the stage mix of both nights.
SET default_transaction_read_only = on;
SET statement_timeout = '30s';
\echo '== 1. every flag/digest audit row since 2026-10-12 00:00 PT (ET time, event, summary, detail)'
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS t_et, event_type, left(summary,160) AS summary, left(detail,300) AS detail
FROM mi_audit_log
WHERE created_at >= TIMESTAMPTZ '2026-10-12 00:00-07' AND (event_type ILIKE '%flag%' OR event_type ILIKE '%digest%')
ORDER BY created_at;
\echo '== 1b. flag_digest_sent ever'
SELECT count(*) n, min(created_at AT TIME ZONE 'America/New_York') first_et, max(created_at AT TIME ZONE 'America/New_York') last_et FROM mi_audit_log WHERE event_type='flag_digest_sent';
\echo '== 2. stage mix by night (rows / holds / WATCH-or-better) 10-09 .. 10-13'
SELECT scan_date, stage, count(*) AS n, count(*) FILTER (WHERE held_from_stage IS NOT NULL) AS holds
FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-09' GROUP BY 1,2 ORDER BY 1,2;
\echo '== 3. the WATCH-or-better rows on 10-12 and 10-13 (ticker, stage, tags)'
SELECT scan_date, ticker, stage, held_from_stage, universe_sources, left(reason,70) reason
FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-12' AND stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED') ORDER BY scan_date, stage, ticker;
\echo '== 4. HOLD at-risk population: tickers whose 10-12 row was TIGHTENING-or-better and not a hold (only these could be held on 10-13)'
SELECT count(*) AS at_risk_for_a_first_hold_on_1013
FROM mi_flag_candidates WHERE scan_date = DATE '2026-10-12' AND stage IN ('TIGHTENING','COILED','TRIGGERED') AND held_from_stage IS NULL;
\echo '== 4b. same, any WATCH-or-better row on 10-12 that dropped on 10-13 (WATCH is the lowest stage; a WATCH drop is INVALIDATED/unqualified, never held)'
SELECT y.ticker, y.stage AS stage_1012, t.stage AS stage_1013, t.held_from_stage
FROM mi_flag_candidates y LEFT JOIN mi_flag_candidates t ON t.ticker=y.ticker AND t.scan_date=DATE '2026-10-13'
WHERE y.scan_date = DATE '2026-10-12' AND y.stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED') ORDER BY 1;
