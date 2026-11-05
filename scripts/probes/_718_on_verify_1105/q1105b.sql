SET default_transaction_read_only = on;
SELECT id, ticker, account_mode, signal_type, status, left(skip_reason,140) skip, entry_order_id FROM mi_live_trades WHERE alert_date = DATE '2026-11-05' ORDER BY id;
SELECT o.alpaca_order_id, o.status, o.side, t.ticker FROM mi_live_orders o JOIN mi_live_trades t ON t.id = o.trade_id WHERE t.alert_date = DATE '2026-11-05';
SELECT ticker, prev_close, created_at AT TIME ZONE 'America/New_York' et FROM mi_ep_scan_log WHERE ticker='CHYM' AND created_at > TIMESTAMPTZ '2026-11-05 12:00+00' ORDER BY created_at DESC LIMIT 2;
SELECT left(detail::text, 600) FROM mi_audit_log WHERE id = 68623;
SELECT id, event_type, created_at AT TIME ZONE 'America/New_York' et, left(summary,160) FROM mi_audit_log WHERE created_at > TIMESTAMPTZ '2026-11-05 14:30+00' AND (summary ILIKE '%APPN%' OR summary ILIKE '%CHYM%') AND event_type NOT ILIKE 'ep_rt_floor%' ORDER BY id LIMIT 20;
