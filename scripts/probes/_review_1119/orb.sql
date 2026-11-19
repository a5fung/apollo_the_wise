SET default_transaction_read_only = on;
SELECT o.*, o.submitted_at AT TIME ZONE 'America/New_York' sub_et, o.cancelled_at AT TIME ZONE 'America/New_York' can_et FROM mi_live_orders o
WHERE o.side='buy' AND o.order_type='stop_limit' AND o.filled_at IS NULL AND o.status IN ('expired','cancelled','canceled') AND o.cancelled_at IS NOT NULL
  AND EXTRACT(EPOCH FROM (o.cancelled_at-o.submitted_at))>4*3600 AND o.submitted_at>'2026-05-28';
