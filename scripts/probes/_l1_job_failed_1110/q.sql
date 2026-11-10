SET default_transaction_read_only = on;
SELECT now() AT TIME ZONE 'America/New_York' AS now_et;
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, summary, left(detail::text, 3000) AS detail
FROM mi_audit_log WHERE event_type LIKE '%_error' AND created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC LIMIT 50;
