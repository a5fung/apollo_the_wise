-- #604 probe: confirm the 16:15 naked_position L1 mechanism on the two
-- historical firings NOT yet traced end-to-end (2026-07-27, 2026-06-23).
-- 2026-08-28 (SOLS) was already traced: entry+stop @ 09:31, DAY stop
-- expired @ 16:00 (stop_order_id_changed reason=cancel_or_reject_null
-- @ 16:05:03, order_status_reconciled ... expired @ 16:15:00), post-close
-- refresh placed the next stop @ 16:20:00 (stop_updated).
--
-- IMPORTANT ASYMMETRY (git log -S "post_close_stop_refresh" -> introduced
-- 2026-08-04, commit 5f628fd8): that 16:20 same-day refresh job did NOT
-- exist on 2026-07-27 or 2026-06-23. Per the #507 comment in trade_stream.py
-- (dated 2026-07-28, the day after the 07-27 firing): before that job
-- existed, nothing re-issued a stop after the 16:00 expiry until the
-- market-hours stop_ack_timeout_watchdog (live since 2026-05-17) picked it
-- up the FOLLOWING morning around 09:00 ET. So Part C below checks the
-- NEXT-MORNING window on both historical dates, not the same-day 16:20
-- slot Part B (08-28-shaped) would look for. Read-only.

-- Part A: the naked_position L1 breach itself, all three dates (08-28
-- included for cross-reference against the already-confirmed case).
SELECT id, created_at, event_type, summary, detail
FROM mi_audit_log
WHERE event_type = 'anomaly_detected'
  AND detail::jsonb ->> 'key' = 'naked_position'
  AND (created_at AT TIME ZONE 'America/New_York')::date
      IN ('2026-07-27', '2026-06-23', '2026-08-28')
ORDER BY created_at;

-- Part B: the SAME-DAY stop lifecycle on the two historical dates, widened
-- to 15:55-16:35 ET so whichever ticker fired that day surfaces without
-- knowing it up front (order_status_reconciled/stop_updated summaries
-- include the ticker directly). Expect to see the 16:00 expiry
-- (stop_order_id_changed reason=cancel_or_reject_null, then
-- order_status_reconciled ... expired) and NOT a same-day stop_updated
-- (that mechanism didn't exist yet) — confirming the asymmetry above rather
-- than assuming the 08-28 shape applies unchanged.
SELECT id,
       created_at,
       (created_at AT TIME ZONE 'America/New_York') AS created_at_et,
       event_type,
       summary
FROM mi_audit_log
WHERE (created_at AT TIME ZONE 'America/New_York')::date
      IN ('2026-07-27', '2026-06-23')
  AND (created_at AT TIME ZONE 'America/New_York')::time
      BETWEEN '15:55:00' AND '16:35:00'
  AND event_type IN (
        'stop_order_id_changed', 'order_status_reconciled', 'stop_updated',
        'naked_position_detected', 'naked_position_remediation_fired',
        'naked_position_remediation_failed', 'anomaly_detected'
      )
ORDER BY created_at;

-- Part C: the NEXT-MORNING re-place window (08:55-09:45 ET on 2026-07-28 and
-- 2026-06-24) — where the stop actually should have been restored pre-08-04,
-- via stop_ack_timeout_watchdog's remediation path.
SELECT id,
       created_at,
       (created_at AT TIME ZONE 'America/New_York') AS created_at_et,
       event_type,
       summary
FROM mi_audit_log
WHERE (created_at AT TIME ZONE 'America/New_York')::date
      IN ('2026-07-28', '2026-06-24')
  AND (created_at AT TIME ZONE 'America/New_York')::time
      BETWEEN '08:55:00' AND '09:45:00'
  AND event_type IN (
        'stop_order_id_changed', 'stop_updated',
        'stop_ack_timeout_remediated', 'stop_ack_remediation_failed',
        'stop_ack_broker_covered', 'stop_ack_broker_unreadable'
      )
ORDER BY created_at;
