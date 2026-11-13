SET default_transaction_read_only = on;
SELECT min(created_at::date), max(created_at::date), count(*) FROM mi_audit_log WHERE event_type='theme_correctness_check' AND detail::text ILIKE '%_truncated%';
SELECT count(*) FROM mi_audit_log WHERE event_type='theme_correctness_check' AND detail::text NOT ILIKE '%_truncated%' AND created_at > now() - interval '30 days';
