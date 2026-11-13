SET default_transaction_read_only = on;
SELECT detail::jsonb->'g3'->'themes'->0 FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at::date='2026-11-11';
