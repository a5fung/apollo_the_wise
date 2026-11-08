SET default_transaction_read_only = on;
SELECT strategy_id, phase, enabled, updated_at FROM mi_strategies WHERE strategy_id='magna53';
SELECT count(*) AS refused_rows, max(created_at) FROM mi_audit_log WHERE event_type='strategy_command_refused';
SELECT state FROM mi_safeguard_state WHERE safeguard='manual_trading_halt';
