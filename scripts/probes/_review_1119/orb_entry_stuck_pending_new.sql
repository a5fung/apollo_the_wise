SET default_transaction_read_only = on;
-- Count ORB entries where status went to expired/canceled with
-- filled_qty=0 AND elapsed >4h (i.e. stuck across the session).
-- Excludes EOD cancellations (orb_unfilled_entry_cleanup at
-- 10:00 ET is intentional + fast). This is the recurring-class
-- detector — RECURRENCE = a POST-FIX occurrence only.
-- WINDOW FIX 2026-06-18 (verified read): a rolling 90d window
-- false-counted the PRE-fix history (RDW 5/26 + 9 April orders
-- the #123 reconcile cancelled in a 5/27 sweep = drift, NOT
-- session stalls) → it read 10 and would have FALSELY BLOCKED
-- the 6/22 cutover gate (RDW still inside the 30d window at 6/22).
-- Floor at the 5/28 watchdog-fix date so this means "has it
-- recurred SINCE the fix?" — verified 0 post-fix on 2026-06-18.
SELECT COUNT(*) FROM mi_live_orders o
WHERE o.side = 'buy'
  AND o.order_type = 'stop_limit'
  AND o.filled_at IS NULL
  AND o.status IN ('expired', 'cancelled', 'canceled')
  AND o.cancelled_at IS NOT NULL
  AND EXTRACT(EPOCH FROM (o.cancelled_at - o.submitted_at)) > 4 * 3600
  AND o.submitted_at > '2026-05-28';  -- post-fix only (was NOW()-90d, pre-fix-contaminated);
