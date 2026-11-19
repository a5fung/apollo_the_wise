SET default_transaction_read_only = on;
SELECT id, ticker, signal_type, account_mode, status, entry_price, entry_shares, partial_taken, highest_price_seen, stop_price, filled_at AT TIME ZONE 'America/New_York' f, closed_at AT TIME ZONE 'America/New_York' c FROM mi_live_trades WHERE id IN (785,788);
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(detail::text,300) FROM mi_audit_log WHERE created_at::date >= '2026-11-18' AND (detail::text LIKE '%"trade_id": 788%' OR detail::text LIKE '%788%') AND created_at < '2026-11-18 16:00:00+00' ORDER BY created_at LIMIT 40;
