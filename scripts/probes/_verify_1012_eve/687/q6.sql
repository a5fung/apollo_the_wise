\echo === Q20 stop_update_retry_* / stop_order_id_changed(cancel_or_reject) around 16:45 on prior days (last 8 days)
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type, left(summary,110) AS summary
FROM mi_audit_log
WHERE created_at >= now() - interval '8 days'
  AND event_type IN ('stop_update_retry_triggered','stop_update_retry_succeeded','stop_updated')
  AND (created_at AT TIME ZONE 'America/New_York')::time BETWEEN '16:44' AND '16:50'
ORDER BY created_at;

\echo === Q21 mi_live_orders statuses of replaced (old) stop rows for open trades 404,414,419
SELECT id, trade_id, ticker, stop_price, status, submitted_at AT TIME ZONE 'America/New_York' AS sub_et, cancelled_at AT TIME ZONE 'America/New_York' AS canc_et, left(alpaca_order_id,8) AS oid
FROM mi_live_orders WHERE trade_id IN (404,414,419) AND purpose='stop_loss' ORDER BY trade_id, id;
