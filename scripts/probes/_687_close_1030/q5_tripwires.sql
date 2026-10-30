SET default_transaction_read_only = on;
\echo == T1 depth sale first fire
SELECT count(*) FROM mi_audit_log WHERE created_at >= DATE '2026-10-12' AND event_type LIKE 'depth_open_sale%';
\echo == T2 flat-broker rulings (i) (a) first fire
SELECT count(*) FROM mi_audit_log WHERE created_at >= DATE '2026-10-04' AND event_type IN ('restore_skipped_broker_flat','coverage_skipped_broker_flat');
\echo == T3 part-filled dead full-exit first fire
SELECT count(*) FROM mi_audit_log WHERE created_at >= DATE '2026-10-14' AND event_type IN ('full_exit_dead_fill_booked','full_exit_dead_fill_duplicate');
\echo == writers alive: depth-marked rows ever, live/paper positions held
SELECT count(*) FILTER (WHERE depth_sell_pending_on IS NOT NULL) AS marked_now, count(*) FILTER (WHERE exit_rule='depth') AS depth_rows FROM mi_live_trades;
