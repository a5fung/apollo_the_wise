SET default_transaction_read_only = on;
SELECT COUNT(*) FROM mi_audit_log
 WHERE created_at >= DATE '2026-09-21'
   AND id <> 79200
   AND (
        event_type IN ('partial_exit_sell_failed', 'partial_exit_rollback_failed')
     OR (event_type = 'partial_exit_aborted'
         AND COALESCE(detail::json->>'stage', '') NOT IN
             ('place_new_stop', 'dedup_pending_exit', 'verify_shares_free'))
     OR (event_type = 'partial_exit_committed'
         AND COALESCE((detail::json->>'new_remaining')::numeric, 0) < 0)
     OR (event_type = 'naked_position_detected'
         AND EXISTS (SELECT 1 FROM mi_audit_log p
                      WHERE p.event_type LIKE 'partial_exit%'
                        AND p.detail::json->>'trade_id' = mi_audit_log.detail::json->>'trade_id'
                        AND p.created_at BETWEEN mi_audit_log.created_at - INTERVAL '1 day'
                                             AND mi_audit_log.created_at))
   );
