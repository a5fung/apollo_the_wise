SET default_transaction_read_only = on;
SELECT created_at::date, length(detail::text) FROM mi_audit_log WHERE event_type='theme_correctness_check' ORDER BY created_at DESC LIMIT 8;
SELECT jsonb_object_keys(detail::jsonb) FROM mi_audit_log WHERE event_type='theme_correctness_check' ORDER BY created_at DESC LIMIT 1;
