SET default_transaction_read_only = on;
SELECT scan_time_et AT TIME ZONE 'America/New_York' AS t, catalyst_quality, llm_catalyst_quality, ep_score, filter_reason, reject_stage
FROM mi_ep_scan_log WHERE ticker='APP' AND scan_date='2026-11-05' ORDER BY id;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,200), left(detail::text,400)
FROM mi_audit_log WHERE created_at BETWEEN '2026-11-05 11:00+00' AND '2026-11-05 21:00+00'
 AND (detail::text ~* '"APP"' OR summary ~* '\mAPP\M') ORDER BY created_at;
