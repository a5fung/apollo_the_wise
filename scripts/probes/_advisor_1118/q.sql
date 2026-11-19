SET default_transaction_read_only = on;
SELECT a.event_type, COALESCE(t.account_mode, a.detail::jsonb->>'account_mode','?') mode, count(*), max(a.created_at)::date
FROM mi_audit_log a LEFT JOIN mi_live_trades t ON t.id = (a.detail::jsonb->>'trade_id')::int
WHERE a.event_type IN ('stop_update_retry_triggered','stop_update_failed','stop_update_retry_succeeded') AND a.created_at > now() - interval '90 days'
GROUP BY 1,2 ORDER BY 1,2;
SELECT detail FROM mi_audit_log WHERE event_type='cot_daily' ORDER BY created_at DESC LIMIT 1;
