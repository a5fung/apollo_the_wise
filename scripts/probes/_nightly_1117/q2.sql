SET default_transaction_read_only = on;
SELECT id, ticker, status, skip_reason, exit_reason, updated_at AT TIME ZONE 'America/New_York' FROM mi_live_trades WHERE id=786;
SELECT created_at AT TIME ZONE 'America/New_York', event_type, summary FROM mi_audit_log WHERE summary LIKE 'CYRX%' AND created_at > NOW() - INTERVAL '12 hours' ORDER BY created_at;
