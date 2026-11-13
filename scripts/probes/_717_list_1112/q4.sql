SET default_transaction_read_only = on;
SELECT count(*) FROM mi_live_trades WHERE signal_type='breakout_v1' AND created_at >= '2026-11-11';
SELECT summary FROM mi_audit_log WHERE event_type='breakout_v1_list_run' ORDER BY created_at DESC LIMIT 1;
