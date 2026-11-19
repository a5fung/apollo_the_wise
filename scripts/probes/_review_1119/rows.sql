SET default_transaction_read_only = on;
\echo ORB_STUCK
SELECT o.id, o.trade_id, o.symbol, o.account_mode, o.submitted_at AT TIME ZONE 'America/New_York' sub, o.cancelled_at AT TIME ZONE 'America/New_York' can, o.status FROM mi_live_orders o
WHERE o.side='buy' AND o.order_type='stop_limit' AND o.filled_at IS NULL AND o.status IN ('expired','cancelled','canceled') AND o.cancelled_at IS NOT NULL
  AND EXTRACT(EPOCH FROM (o.cancelled_at-o.submitted_at))>4*3600 AND o.submitted_at>'2026-05-28';
\echo PARTIAL
SELECT id, event_type, created_at AT TIME ZONE 'America/New_York', left(detail::text,400) FROM mi_audit_log
 WHERE created_at >= DATE '2026-09-21' AND (event_type IN ('partial_exit_sell_failed','partial_exit_rollback_failed')
  OR (event_type='partial_exit_aborted' AND COALESCE(detail::json->>'stage','') NOT IN ('place_new_stop','dedup_pending_exit','verify_shares_free'))
  OR (event_type='partial_exit_committed' AND COALESCE((detail::json->>'new_remaining')::numeric,0)<0)
  OR (event_type='naked_position_detected' AND EXISTS (SELECT 1 FROM mi_audit_log p WHERE p.event_type LIKE 'partial_exit%' AND p.detail::json->>'trade_id'=mi_audit_log.detail::json->>'trade_id' AND p.created_at BETWEEN mi_audit_log.created_at-INTERVAL '1 day' AND mi_audit_log.created_at)));
\echo STOPROW
SELECT id, event_type, created_at AT TIME ZONE 'America/New_York', left(detail::text,500) FROM mi_audit_log
WHERE event_type IN ('naked_position_detected','stop_placement_failed_after_partial','entry_fill_stop_remediated') AND created_at > NOW()-INTERVAL '14 days';
\echo EXTCAP
SELECT scan_date, ticker, filter_reason FROM mi_ep_scan_log WHERE filter_reason ILIKE '%(extended)%' AND scan_date >= DATE '2026-08-23' AND scan_date < CURRENT_DATE-5
 AND NULLIF(regexp_replace(filter_reason,'^already up ([0-9.]+)%.*$','\1'),filter_reason)::numeric >= 50
 AND NULLIF(regexp_replace(filter_reason,'^already up ([0-9.]+)%.*$','\1'),filter_reason)::numeric < 75 ORDER BY scan_date;
