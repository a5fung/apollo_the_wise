SET default_transaction_read_only = on;
\echo == depth sale audit rows
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(detail::text, 900) FROM mi_audit_log WHERE created_at >= DATE '2026-10-12' AND event_type LIKE 'depth_open_sale%' ORDER BY created_at;
\echo == depth marks / pending
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(detail::text, 400) FROM mi_audit_log WHERE created_at > NOW() - INTERVAL '2 days' AND (event_type ILIKE '%depth%') ORDER BY created_at;
\echo == the trades named
SELECT id, ticker, account_mode, signal_type, status, exit_rule, shares, remaining_shares, fill_price, exit_price_final, closed_at AT TIME ZONE 'America/New_York' AS closed_et, depth_sell_pending_on FROM mi_live_trades WHERE status IN ('filled','closed') AND exit_rule = 'depth' AND (closed_at IS NULL OR closed_at > NOW() - INTERVAL '3 days') ORDER BY id;
