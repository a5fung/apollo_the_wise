SET default_transaction_read_only = on;
SELECT event_type, created_at, length(detail::text), left(summary,120) FROM mi_audit_log WHERE created_at > now() - interval '6 hours' AND detail::text ILIKE '%_truncated%' ORDER BY created_at DESC LIMIT 5;
