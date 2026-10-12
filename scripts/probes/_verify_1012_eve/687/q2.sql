\echo === Q5 audit rows 16:45 window (live_position_update) detail
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, summary, left(detail,700) AS detail
FROM mi_audit_log WHERE created_at >= (timestamp '2026-10-12 16:44' AT TIME ZONE 'America/New_York') AND created_at < (timestamp '2026-10-12 16:50' AT TIME ZONE 'America/New_York')
 AND event_type IN ('dead_stop_price_preserved','stop_order_id_changed','stop_replacement_confirmed_silent','stop_updated','stop_update_retry_succeeded','stop_update_retry_triggered','stop_update_started') ORDER BY id;

\echo === Q6 drift_check_snapshot 18:02
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, summary, left(detail,3000) AS detail FROM mi_audit_log WHERE event_type='drift_check_snapshot' AND created_at >= (timestamp '2026-10-12 18:00' AT TIME ZONE 'America/New_York') ORDER BY id;

\echo === Q7 entry_partial_fill + coverage_drift_detected + depth/exit-related today
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, summary, left(detail,900) AS detail
FROM mi_audit_log WHERE created_at >= (timestamp '2026-10-12 09:00' AT TIME ZONE 'America/New_York')
 AND (event_type IN ('entry_partial_fill','coverage_drift_detected','ep_rt_admit') OR event_type ILIKE '%depth%' OR event_type ILIKE '%stop_breach%' OR event_type ILIKE '%restore%' OR event_type ILIKE '%unprotected%' OR event_type ILIKE '%naked%' OR event_type ILIKE '%expir%') ORDER BY id;

\echo === Q8 live orders created today
SELECT o.id, o.trade_id, o.ticker, o.side, o.order_type, o.qty, o.stop_price, o.limit_price, o.status, o.filled_qty, o.filled_avg_price, o.purpose, o.exit_reason, o.submitted_at AT TIME ZONE 'America/New_York' AS sub_et
FROM mi_live_orders o WHERE o.submitted_at >= (timestamp '2026-10-12 00:00' AT TIME ZONE 'America/New_York') ORDER BY o.id;

\echo === Q9 tables with alert in the name
SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND (table_name ILIKE '%ep_alert%' OR table_name ILIKE '%ep_detect%' OR table_name ILIKE '%entry%') ORDER BY 1;
