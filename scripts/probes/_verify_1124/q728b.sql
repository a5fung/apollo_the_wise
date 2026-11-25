SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,170), left(detail::text,220) FROM mi_audit_log
WHERE created_at >= '2026-11-24 09:00-05' AND (event_type LIKE 'stop_%' OR event_type LIKE '%replace%' OR detail::text ILIKE '%price_only_replace%') ORDER BY created_at;
