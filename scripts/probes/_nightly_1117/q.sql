SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York', summary, left(detail::text, 600) FROM mi_audit_log WHERE event_type='breakout_v1_cancel_failed' ORDER BY created_at DESC LIMIT 5;
SELECT id, created_at, jsonb_typeof(detail), left(detail::text,200) FROM mi_cot_alerts ORDER BY id DESC LIMIT 8;
