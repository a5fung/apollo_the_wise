\pset pager off
\pset null '-'
\pset format unaligned
\pset fieldsep ' | '
-- (a) rare / decisive events in window, full detail (ET timestamps)
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,300) AS summary, left(detail,700) AS detail
FROM mi_audit_log
WHERE created_at >= '2026-09-12' AND created_at < '2026-10-13 14:00+00'
  AND event_type IN ('full_exit_rejected','full_exit_committed','full_exit_sized_around_resting_exit','planned_sale_stop_cancel',
                     'stop_cancel_by_planned_sale_silent','stop_remediation_skipped_pending_exit','stop_coverage_repaired',
                     'stop_coverage_repair_failed','stop_coverage_retry_attempted','stop_ack_broker_covered','stop_ack_timeout_remediated',
                     'stop_update_aborted','stop_pointer_repair_deferred','partial_exit_stop_replaced','position_unprotected',
                     'position_unprotected_check_failed','stop_ack_remediation_failed','naked_position_detected','naked_position_remediation_failed',
                     'cancel_or_reject_restored','stop_pointer_repaired','stop_restore_retried','stop_restore_retry_ended','restore_skipped_broker_flat',
                     'stop_breach_market_sale','stop_breach_sale_failed','stop_breach_sale_skipped','stop_coverage_breach','stop_coverage_ambiguous',
                     'stop_coverage_no_price','stop_coverage_adopted','stop_coverage_repair_failed')
ORDER BY created_at;

-- (b) every audit row at or after 15:55 ET and before 09:00 ET next day whose event type matches position-protection words,
--     EXCLUDING the routine 16:45 stop-cycle events counted separately below
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,200) AS summary
FROM mi_audit_log
WHERE created_at >= '2026-09-12' AND created_at < '2026-10-13 14:00+00'
  AND event_type ~* '(unprot|naked|orphan|remed|restor|reprot|backstop|stop_ack|pointer|repair|breach|exit_rej|cancel_or_reject)'
  AND event_type NOT IN ('theme_orphan_sub','theme_orphan_sub_mechanism','backup_restore_check_ok','themes_restored')
ORDER BY created_at;

-- (c) stop_order_id_changed: reason x new_id-null distribution, then every NULL-new_id row and every non-routine reason
SELECT (detail::jsonb->>'reason') AS reason, (detail::jsonb->>'new_id' IS NULL) AS new_is_null, count(*) AS n,
       min(created_at AT TIME ZONE 'America/New_York') AS first_et, max(created_at AT TIME ZONE 'America/New_York') AS last_et
FROM mi_audit_log WHERE event_type='stop_order_id_changed' AND created_at >= '2026-09-12' AND created_at < '2026-10-13 14:00+00'
GROUP BY 1,2 ORDER BY 1,2;

SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, summary
FROM mi_audit_log WHERE event_type='stop_order_id_changed' AND created_at >= '2026-09-12' AND created_at < '2026-10-13 14:00+00'
  AND (detail::jsonb->>'new_id' IS NULL OR (detail::jsonb->>'reason') NOT IN ('stop_update_succeeded','partial_replacement'))
ORDER BY created_at;

-- (d) after-16:00 audit rows (ET) between 16:00 and 21:30 on any trading night whose event_type mentions stop/position/exit/coverage/sync (not path/theme noise), count by type
SELECT event_type, count(*) AS n
FROM mi_audit_log
WHERE created_at >= '2026-09-14' AND created_at < '2026-10-13 12:00+00'
  AND (created_at AT TIME ZONE 'America/New_York')::time BETWEEN '16:00' AND '21:30'
  AND extract(isodow FROM created_at AT TIME ZONE 'America/New_York') < 6
  AND event_type ~* '(stop|position|exit|cover|sync|trade|order|fill|broker|alpaca)'
  AND event_type NOT IN ('path_coverage_gap','coverage_probe_ran')
GROUP BY 1 ORDER BY 1;

-- (e) the 16:45 stop cycle: per night counts of started/updated/retry/replacement-confirmed rows and any dead_stop_price_preserved
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d,
  count(*) FILTER (WHERE event_type='stop_update_started') AS started,
  count(*) FILTER (WHERE event_type='stop_updated') AS updated,
  count(*) FILTER (WHERE event_type='stop_update_retry_triggered') AS retry_trig,
  count(*) FILTER (WHERE event_type='stop_update_retry_succeeded') AS retry_ok,
  count(*) FILTER (WHERE event_type='stop_replacement_confirmed_silent') AS repl_conf,
  count(*) FILTER (WHERE event_type='dead_stop_price_preserved') AS dead_preserved,
  count(*) FILTER (WHERE event_type='stop_update_aborted') AS aborted
FROM mi_audit_log
WHERE created_at >= '2026-09-14' AND created_at < '2026-10-13 12:00+00'
  AND (created_at AT TIME ZONE 'America/New_York')::time BETWEEN '16:40' AND '16:50'
  AND event_type IN ('stop_update_started','stop_updated','stop_update_retry_triggered','stop_update_retry_succeeded','stop_replacement_confirmed_silent','dead_stop_price_preserved','stop_update_aborted')
GROUP BY 1 ORDER BY 1;
