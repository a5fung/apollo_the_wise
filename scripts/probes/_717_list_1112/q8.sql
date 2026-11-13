SET default_transaction_read_only = on;
SELECT k, length(v::text) FROM mi_audit_log, jsonb_each(detail::jsonb) AS e(k,v) WHERE event_type='theme_correctness_check' AND created_at::date='2026-11-11' ORDER BY 2 DESC LIMIT 8;
