SET default_transaction_read_only = on;
SELECT a.created_at::date d, t.ticker, a.detail::jsonb->>'new_stop_price' px, left(a.detail::jsonb->>'error_first',90) err FROM mi_audit_log a JOIN mi_live_trades t ON t.id=(a.detail::jsonb->>'trade_id')::int WHERE a.event_type='stop_update_failed' AND t.account_mode='live' AND a.created_at > now()-interval '90 days' ORDER BY 1;
