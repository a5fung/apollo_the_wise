\pset pager off
-- V3 peek: detail key sets of the event types I will join on (one sample + key census)
SELECT event_type, k, count(*) FROM mi_audit_log, jsonb_object_keys(detail::jsonb) k
WHERE created_at >= '2026-09-12' AND detail ~ '^\s*\{'
  AND event_type IN ('stop_order_id_changed','stop_refresh_ran','stop_replacement_confirmed_silent','stop_updated','full_exit_rejected',
                     'stop_ack_timeout_remediated','stop_coverage_repaired','stop_remediation_skipped_pending_exit','planned_sale_stop_cancel','dead_stop_price_preserved')
GROUP BY 1,2 ORDER BY 1,2;
SELECT event_type, created_at AT TIME ZONE 'America/New_York' AS et, left(summary,250) AS summary, left(detail,600) AS detail
FROM mi_audit_log WHERE id IN (
  SELECT max(id) FROM mi_audit_log WHERE created_at >= '2026-09-12'
    AND event_type IN ('stop_order_id_changed','stop_refresh_ran','stop_replacement_confirmed_silent','dead_stop_price_preserved') GROUP BY event_type);
