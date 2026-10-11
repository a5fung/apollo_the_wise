-- SELECT-only. #687 (c) review finding 1: has an ORDERS-ENDPOINT market sell ever been submitted
-- after the close on a PAPER book, and what did the broker do with it? (the 19:01 depth sale is one)
SELECT o.id, o.alpaca_order_id, o.ticker, t.account_mode, o.order_type, o.purpose, o.exit_reason,
       o.status, o.qty, o.filled_qty,
       to_char(o.submitted_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD Dy HH24:MI:SS') AS submitted_et,
       to_char(o.filled_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD Dy HH24:MI:SS') AS filled_et,
       o.raw_response->>'time_in_force' AS tif
FROM mi_live_orders o
JOIN mi_live_trades t ON t.id = o.trade_id
WHERE o.side = 'sell' AND o.order_type = 'market'
  AND (extract(hour FROM o.submitted_at AT TIME ZONE 'America/New_York') >= 16
       OR extract(hour FROM o.submitted_at AT TIME ZONE 'America/New_York') < 9
       OR extract(dow FROM o.submitted_at AT TIME ZONE 'America/New_York') IN (0, 6))
ORDER BY o.submitted_at DESC
LIMIT 40;
