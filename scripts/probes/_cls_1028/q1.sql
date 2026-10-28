SET default_transaction_read_only = on;
SELECT id, ticker, account_mode, status, alert_date, entry_price, remaining_shares, hard_stop, stop_price,
       partial_taken, breakeven_active, exit_rule, hold_days, depth_sell_pending_on, jsonb_array_length(running_closes) AS n_closes, running_closes
FROM mi_live_trades WHERE ticker='CLS' AND status IN ('filled','partial') ORDER BY id DESC LIMIT 3;
SELECT (created_at AT TIME ZONE 'America/New_York')::timestamp(0) AS et, event_type, left(details::text, 300) AS details
FROM mi_audit_log WHERE details::text LIKE '%"CLS"%' AND created_at > now() - interval '7 days'
ORDER BY created_at DESC LIMIT 20;
