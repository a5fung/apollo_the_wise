SET default_transaction_read_only = on;
SELECT count(*) FROM mi_trades WHERE signal_type='breakout_v1' AND created_at >= '2026-11-11';
SELECT event_type, left(summary,140), created_at FROM mi_audit_log WHERE created_at > now() - interval '3 hours' AND event_type ILIKE 'breakout_v1%' ORDER BY created_at DESC LIMIT 3;
