-- the buyout screen: mna_filter_fired rows from the flag detector since the 10-04 deploy (all stages)
SELECT created_at AT TIME ZONE 'America/New_York' AS et, summary, LEFT(detail,600) AS detail
FROM mi_audit_log
WHERE event_type='mna_filter_fired' AND created_at >= '2026-10-04'
  AND (summary LIKE '%(flag)%' OR detail LIKE '%''detector'': ''flag''%')
ORDER BY created_at;
SELECT '--- flag-candidate rows demoted by the screen since 10-04 (persisted side) ---' AS x;
SELECT scan_date, ticker, stage, reason, held_from_stage
FROM mi_flag_candidates
WHERE scan_date >= '2026-10-04' AND reason LIKE 'mna_filter:%'
ORDER BY scan_date, ticker;
SELECT '--- other mna_* events since 10-04 touching flag tickers (headline lookups) ---' AS x;
SELECT event_type, count(*) n, min(created_at AT TIME ZONE 'America/New_York') first_et, max(created_at AT TIME ZONE 'America/New_York') last_et
FROM mi_audit_log WHERE event_type LIKE 'mna%' AND created_at >= '2026-10-04'
GROUP BY 1 ORDER BY 1;
