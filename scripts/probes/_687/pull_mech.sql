-- #687 part 3 read-only prod capture (ONE round-trip, READ ONLY transaction, rolled back): how today's exit orders behave live.
BEGIN TRANSACTION READ ONLY;
\echo === FULL_EXIT_ORDERS ===
SELECT o.trade_id, o.ticker, t.account_mode, o.order_type, o.status, o.exit_reason, o.qty,
       (to_jsonb(o) ->> 'created_at') AS created_at,
       (o.raw_response ->> 'time_in_force') AS tif, (o.raw_response ->> 'submitted_at') AS submitted_at,
       (o.raw_response ->> 'filled_at') AS filled_at_raw, (o.raw_response ->> 'filled_avg_price') AS fill_px_raw
FROM mi_live_orders o JOIN mi_live_trades t ON t.id = o.trade_id
WHERE o.purpose = 'full_exit' ORDER BY o.trade_id;
\echo === SMA_TRAIL_EXITS ===
SELECT t.id, t.ticker, t.account_mode, t.signal_type, t.alert_date, t.status,
       e ->> 'time' AS exit_time, e ->> 'price' AS exit_px, e ->> 'reason' AS reason, e ->> 'shares' AS shares
FROM mi_live_trades t, jsonb_array_elements(CASE WHEN jsonb_typeof(t.exits) = 'array' THEN t.exits ELSE '[]'::jsonb END) e
WHERE e ->> 'reason' IN ('sma_trail_stop', 'close_below_line') ORDER BY t.id;
\echo === PARTIAL_EXIT_ORDERS ===
SELECT o.trade_id, o.ticker, t.account_mode, o.order_type, o.status, o.limit_price, o.qty,
       (o.raw_response ->> 'order_class') AS order_class, (o.raw_response ->> 'submitted_at') AS submitted_at,
       (o.raw_response ->> 'filled_at') AS filled_at_raw, (to_jsonb(o) ->> 'created_at') AS created_at
FROM mi_live_orders o JOIN mi_live_trades t ON t.id = o.trade_id
WHERE o.purpose = 'partial_exit' AND (to_jsonb(o) ->> 'created_at') >= '2026-08-10' ORDER BY o.trade_id;
\echo === OPEN_POSITIONS ===
SELECT id, ticker, account_mode, signal_type, alert_date, entry_price, hard_stop, stop_price, remaining_shares,
       partial_taken, breakeven_active, stop_order_id IS NOT NULL AS has_stop_ptr
FROM mi_live_trades WHERE status = 'filled' AND remaining_shares > 0 ORDER BY account_mode, id;
\echo === FULL_EXIT_AUDIT ===
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary, 240) AS summary
FROM mi_audit_log WHERE event_type IN ('full_exit_rejected') OR summary ILIKE 'Full exit%' OR summary ILIKE '%full exit%'
ORDER BY created_at DESC LIMIT 40;
ROLLBACK;
