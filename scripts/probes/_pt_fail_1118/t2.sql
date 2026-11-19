SET default_transaction_read_only = on;
SELECT id, ticker, status, entry_shares, remaining_shares, stop_price, stop_order_id, hard_stop FROM mi_live_trades WHERE id IN (785,788);
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(detail::text,400) FROM mi_audit_log WHERE created_at >= '2026-11-18 14:53:00+00' AND (detail::text LIKE '%"trade_id": 788%' OR detail::text LIKE '%trade_id=788%' OR detail::text LIKE '%CAKE%') ORDER BY created_at LIMIT 40;
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(detail::text,300) FROM mi_audit_log WHERE created_at >= '2026-11-18 14:44:00+00' AND created_at < '2026-11-18 14:47:00+00' AND detail::text LIKE '%785%' ORDER BY created_at;
