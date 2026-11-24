SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,160), left(detail::text,200) FROM mi_audit_log
WHERE created_at >= '2026-11-23 16:00-05' AND (event_type LIKE 'stop_%' OR event_type LIKE '%replace%' OR event_type LIKE 'breakout_pp%' OR event_type LIKE 'naked%') ORDER BY created_at;
