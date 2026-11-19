SET default_transaction_read_only = on;
-- TODO: add explicit audit events at trade_stream.py:367 and
-- :600-611 so this predicate is specific. For now uses
-- naked-position proxy (fires if either branch's stop also
-- fails to actually be placed at broker).
SELECT COUNT(*) FROM mi_audit_log
WHERE event_type IN ('naked_position_detected',
                      'stop_placement_failed_after_partial',
                      'entry_fill_stop_remediated')
  AND created_at > NOW() - INTERVAL '14 days';
