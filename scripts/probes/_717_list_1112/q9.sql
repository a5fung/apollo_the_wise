SET default_transaction_read_only = on;
SELECT k, jsonb_typeof(v), length(v::text), CASE WHEN jsonb_typeof(v)='array' THEN jsonb_array_length(v) END FROM mi_audit_log, jsonb_each(detail::jsonb->'g3') AS e(k,v) WHERE event_type='theme_correctness_check' AND created_at::date='2026-11-11' ORDER BY 3 DESC LIMIT 6;
