\pset pager off
\pset null '-'
-- KOD (#404): the 15 night-slots (09-28..10-02) where the order mirror's newest stop_loss row had ended before the slot.
-- Is the 4-sh replacement stop fada5284 (partial_exit_stop_replaced 09-28 10:10) in the mirror under another purpose/type?
SELECT left(alpaca_order_id,8) AS oid, side, order_type, purpose, status, qty, stop_price, submitted_at AT TIME ZONE 'America/New_York' AS sub_et, cancelled_at AT TIME ZONE 'America/New_York' AS canc_et, filled_at AT TIME ZONE 'America/New_York' AS fill_et
FROM mi_live_orders WHERE trade_id=404 ORDER BY submitted_at;
SELECT count(*) AS rows_with_fada5284 FROM mi_live_orders WHERE alpaca_order_id LIKE 'fada5284%';
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,200) AS summary
FROM mi_audit_log WHERE created_at >= '2026-09-28' AND created_at < '2026-10-06' AND (summary ILIKE '%KOD%' OR detail ILIKE '%"trade_id": 404%') ORDER BY created_at;
