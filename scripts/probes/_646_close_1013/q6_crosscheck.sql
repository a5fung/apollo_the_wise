\pset pager off
\pset null '-'
-- (1) audit-row `examined` vs positions held per mi_live_trades (live), per night x slot. Mismatches listed; summary count.
WITH days AS (
  SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d) < 6
), slots AS (
  SELECT d, nm, ev, ((d + t) AT TIME ZONE 'America/New_York') AS ts
  FROM days, (VALUES ('1700','coverage_checked_post_close', time '17:00'),('1900','coverage_checked_late', time '19:00'),('2110','coverage_verified_evening', time '21:10')) s(nm,ev,t)
), held AS (
  SELECT s.d, s.nm, count(t.id) AS held_n
  FROM slots s LEFT JOIN mi_live_trades t
    ON t.account_mode='live' AND t.filled_at IS NOT NULL AND t.filled_at < s.ts AND (t.closed_at IS NULL OR t.closed_at > s.ts)
  GROUP BY 1,2
), aud AS (
  SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type, max((detail::jsonb->>'examined')::int) AS ex, max((detail::jsonb->>'covered')::int) AS cov
  FROM mi_audit_log WHERE event_type IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening')
    AND created_at >= '2026-09-14' AND created_at < '2026-10-13 12:00+00' GROUP BY 1,2
)
SELECT count(*) AS night_slots, count(*) FILTER (WHERE a.ex IS NOT NULL) AS audit_row_present,
       count(*) FILTER (WHERE a.ex = h.held_n) AS examined_equals_held, count(*) FILTER (WHERE a.ex <> h.held_n OR a.ex IS NULL) AS mismatches,
       count(*) FILTER (WHERE h.held_n > 0) AS slots_with_live_shares_held, count(*) FILTER (WHERE h.held_n > 0 AND a.ex > 0) AS of_which_examined_pos,
       sum(h.held_n) AS total_held_position_slots, sum(a.ex) AS total_examined, sum(a.cov) AS total_covered
FROM slots s JOIN held h ON h.d=s.d AND h.nm=s.nm LEFT JOIN aud a ON a.d=s.d AND a.event_type=s.ev;

-- (2) INDEPENDENT corroboration from the order mirror (WS/REST-fed, different code path than the detector's REST poll):
--     for each held live position at each slot, is the newest stop_loss order submitted by that time still live then?
WITH days AS (
  SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d) < 6
), slots AS (
  SELECT d, nm, ((d + t) AT TIME ZONE 'America/New_York') AS ts FROM days, (VALUES ('1700', time '17:00'),('1900', time '19:00'),('2110', time '21:10')) s(nm,t)
), held AS (
  SELECT s.d, s.nm, s.ts, t.id AS trade_id, t.ticker FROM slots s JOIN mi_live_trades t
    ON t.account_mode='live' AND t.filled_at IS NOT NULL AND t.filled_at < s.ts AND (t.closed_at IS NULL OR t.closed_at > s.ts)
), newest AS (
  SELECT h.*, o.status AS o_status, o.submitted_at AS o_sub, o.cancelled_at, o.filled_at AS o_filled, o.stop_price AS o_stop, o.qty AS o_qty,
         row_number() OVER (PARTITION BY h.d, h.nm, h.trade_id ORDER BY o.submitted_at DESC) AS rn
  FROM held h LEFT JOIN mi_live_orders o
    ON o.trade_id=h.trade_id AND o.side ILIKE 'sell%' AND o.order_type ILIKE '%stop%' AND o.purpose='stop_loss' AND o.submitted_at <= h.ts
), j AS (
  SELECT *, CASE
      WHEN o_status IS NULL THEN 'no_stop_order_in_mirror'
      WHEN o_status IN ('new','replaced') THEN 'live'
      WHEN o_status IN ('canceled','cancelled') AND cancelled_at > ts THEN 'live'
      WHEN o_status = 'filled' AND o_filled > ts THEN 'live'
      WHEN o_status = 'expired' THEN 'expired_before_slot'
      ELSE 'ended_before_slot' END AS verdict
  FROM newest WHERE rn=1
)
SELECT nm, verdict, count(*) AS position_slots FROM j GROUP BY 1,2 ORDER BY 1,2;

SELECT d, nm, ticker, verdict, o_status, o_sub AT TIME ZONE 'America/New_York' AS stop_submitted_et, cancelled_at AT TIME ZONE 'America/New_York' AS cancelled_et, o_stop, o_qty
FROM (
  WITH days AS (SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d) < 6),
  slots AS (SELECT d, nm, ((d + t) AT TIME ZONE 'America/New_York') AS ts FROM days, (VALUES ('1700', time '17:00'),('1900', time '19:00'),('2110', time '21:10')) s(nm,t)),
  held AS (SELECT s.d, s.nm, s.ts, t.id AS trade_id, t.ticker FROM slots s JOIN mi_live_trades t ON t.account_mode='live' AND t.filled_at IS NOT NULL AND t.filled_at < s.ts AND (t.closed_at IS NULL OR t.closed_at > s.ts)),
  newest AS (SELECT h.*, o.status AS o_status, o.submitted_at AS o_sub, o.cancelled_at, o.filled_at AS o_filled, o.stop_price AS o_stop, o.qty AS o_qty,
             row_number() OVER (PARTITION BY h.d, h.nm, h.trade_id ORDER BY o.submitted_at DESC) AS rn
             FROM held h LEFT JOIN mi_live_orders o ON o.trade_id=h.trade_id AND o.side ILIKE 'sell%' AND o.order_type ILIKE '%stop%' AND o.purpose='stop_loss' AND o.submitted_at <= h.ts)
  SELECT *, CASE WHEN o_status IS NULL THEN 'no_stop_order_in_mirror' WHEN o_status IN ('new','replaced') THEN 'live'
      WHEN o_status IN ('canceled','cancelled') AND cancelled_at > ts THEN 'live' WHEN o_status='filled' AND o_filled > ts THEN 'live'
      WHEN o_status='expired' THEN 'expired_before_slot' ELSE 'ended_before_slot' END AS verdict
  FROM newest WHERE rn=1
) z WHERE verdict <> 'live' ORDER BY d, nm, ticker;

-- (3) POSITIVE CONTROL: has this same detector EVER written a gap row? (all time)
SELECT event_type, count(*) AS n, min(created_at AT TIME ZONE 'America/New_York') AS first_et, max(created_at AT TIME ZONE 'America/New_York') AS last_et
FROM mi_audit_log WHERE event_type IN ('position_unprotected','position_unprotected_check_failed','coverage_checked_post_close','coverage_checked_late','coverage_verified_evening',
  'coverage_checked_post_close_repair_attempted','coverage_checked_late_repair_attempted','naked_position_detected','stop_ack_remediation_failed','full_exit_rejected','restored_after_failed_full_exit')
GROUP BY 1 ORDER BY 1;
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,200) AS summary
FROM mi_audit_log WHERE event_type IN ('position_unprotected','position_unprotected_check_failed','naked_position_detected','stop_ack_remediation_failed') ORDER BY created_at DESC LIMIT 12;

-- (4) the 16:45 live NULL -> restored pairing, summarised
WITH ev AS (
  SELECT id, created_at, (detail::jsonb->>'trade_id')::int AS trade_id, detail::jsonb->>'new_id' AS new_id, detail::jsonb->>'reason' AS reason, detail::jsonb->>'account_mode' AS mode
  FROM mi_audit_log WHERE event_type='stop_order_id_changed' AND created_at >= '2026-09-14' AND created_at < '2026-10-13 12:00+00'
), n AS (
  SELECT e.*, (SELECT extract(epoch FROM (e2.created_at-e.created_at)) FROM ev e2 WHERE e2.trade_id=e.trade_id AND e2.new_id IS NOT NULL AND e2.created_at>e.created_at ORDER BY e2.created_at LIMIT 1) AS secs
  FROM ev e WHERE e.new_id IS NULL AND e.mode='live'
)
SELECT (created_at AT TIME ZONE 'America/New_York')::time(0) >= '16:40' AND (created_at AT TIME ZONE 'America/New_York')::time(0) < '16:50' AS is_1645_cycle,
       count(*) AS live_null_events, count(*) FILTER (WHERE secs <= 10) AS restored_within_10s, max(secs) FILTER (WHERE secs <= 3600) AS max_secs_when_restored_within_1h
FROM n GROUP BY 1;
