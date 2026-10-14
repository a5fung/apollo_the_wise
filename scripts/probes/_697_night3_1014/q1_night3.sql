-- READ-ONLY. Night 3 specifics: the hold test population (10-13 TIGHTENING-or-better, not a hold) and what each did on 10-14,
-- every hold row, the audit trail since 10-13 evening, stage mix, WATCH-or-better rows of both nights.
SET default_transaction_read_only = on;
SET statement_timeout = '30s';
\echo '== 1. every flag/digest/hold audit row since 2026-10-13 12:00 PT (ET time, event, summary, detail)'
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS t_et, event_type, left(summary,160) AS summary, left(detail,330) AS detail
FROM mi_audit_log
WHERE created_at >= TIMESTAMPTZ '2026-10-13 12:00-07' AND (event_type ILIKE '%flag%' OR event_type ILIKE '%digest%' OR event_type ILIKE '%hold%')
ORDER BY created_at;
\echo '== 1b. flag_digest_sent ever, and flag_stage_flip_held ever + since 10-12'
SELECT event_type, count(*) n, to_char(min(created_at) AT TIME ZONE 'America/New_York','MM-DD HH24:MI') first_et, to_char(max(created_at) AT TIME ZONE 'America/New_York','MM-DD HH24:MI') last_et
FROM mi_audit_log WHERE event_type IN ('flag_digest_sent','flag_stage_flip_held') GROUP BY 1 ORDER BY 1;
\echo '== 2. stage mix by night 10-12 .. 10-14 (rows / holds)'
SELECT scan_date, stage, count(*) AS n, count(*) FILTER (WHERE held_from_stage IS NOT NULL) AS holds
FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-12' GROUP BY 1,2 ORDER BY 1,2;
\echo '== 3. WATCH-or-better rows on 10-13 and 10-14 (ticker, stage, held_from, tags, reason)'
SELECT scan_date, ticker, stage, held_from_stage, universe_sources, left(reason,90) reason
FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-13' AND stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED') ORDER BY scan_date, stage, ticker;
\echo '== 4. HOLD at-risk population: tickers whose 10-13 row was TIGHTENING-or-better and not a hold -> their 10-14 row (ANY stage, incl. unqualified/INVALIDATED/no row)'
SELECT y.ticker, y.stage AS stage_1013, t.stage AS stage_1014, t.held_from_stage, left(t.reason,100) AS reason_1014, t.universe_sources AS src_1014
FROM mi_flag_candidates y LEFT JOIN mi_flag_candidates t ON t.ticker=y.ticker AND t.scan_date=DATE '2026-10-14'
WHERE y.scan_date = DATE '2026-10-13' AND y.stage IN ('TIGHTENING','COILED','TRIGGERED') AND y.held_from_stage IS NULL ORDER BY 1;
\echo '== 4b. same for every WATCH-or-better row on 10-13 (WATCH is the lowest stage: a WATCH drop is INVALIDATED/unqualified, never held)'
SELECT y.ticker, y.stage AS stage_1013, t.stage AS stage_1014, t.held_from_stage
FROM mi_flag_candidates y LEFT JOIN mi_flag_candidates t ON t.ticker=y.ticker AND t.scan_date=DATE '2026-10-14'
WHERE y.scan_date = DATE '2026-10-13' AND y.stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED') ORDER BY 1;
\echo '== 5. every hold row written 10-12 or later'
SELECT scan_date, ticker, stage, held_from_stage, left(reason,100) reason FROM mi_flag_candidates WHERE held_from_stage IS NOT NULL AND scan_date >= DATE '2026-10-12' ORDER BY 1,2;
\echo '== 6. IOVA and GRAL last 5 rows (full)'
SELECT ticker, scan_date, stage, held_from_stage, base_age, failed_at, universe_sources, left(reason,110) reason
FROM mi_flag_candidates WHERE ticker IN ('IOVA','GRAL') AND scan_date >= DATE '2026-10-08' ORDER BY ticker, scan_date;
\echo '== 7. fingerprint: ticker with a hold on its prior row and a fallen stage on 10-14'
SELECT t.ticker, p.scan_date AS prior_date, p.stage AS prior_stage, p.held_from_stage AS prior_held_from, t.stage AS stage_d, t.held_from_stage AS held_d
FROM mi_flag_candidates t
JOIN LATERAL (SELECT * FROM mi_flag_candidates x WHERE x.ticker=t.ticker AND x.scan_date < t.scan_date AND x.scan_date >= t.scan_date - 5 ORDER BY x.scan_date DESC LIMIT 1) p ON true
WHERE t.scan_date = DATE '2026-10-14' AND p.held_from_stage IS NOT NULL;
