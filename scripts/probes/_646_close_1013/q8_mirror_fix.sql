\pset pager off
\pset null '-'
-- FIX of q6 section (2): q6 looked only at the NEWEST stop_loss row by submitted_at, which for KOD (09-28..10-02) was the 1-share OCO sibling
-- stop that was cancelled in 4 s, hiding the live 4-share stop fada5284. Correct test: does ANY stop_loss row of the trade cover the slot?
WITH days AS (
  SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d) < 6
), slots AS (
  SELECT d, nm, ((d + t) AT TIME ZONE 'America/New_York') AS ts FROM days, (VALUES ('1700', time '17:00'),('1900', time '19:00'),('2110', time '21:10')) s(nm,t)
), held AS (
  SELECT s.d, s.nm, s.ts, t.id AS trade_id, t.ticker FROM slots s JOIN mi_live_trades t
    ON t.account_mode='live' AND t.filled_at IS NOT NULL AND t.filled_at < s.ts AND (t.closed_at IS NULL OR t.closed_at > s.ts)
), liveord AS (
  SELECT h.d, h.nm, h.ticker, h.trade_id, o.alpaca_order_id, o.status, o.qty,
         ( o.status='new'
           OR (o.status IN ('canceled','cancelled') AND o.cancelled_at > h.ts)
           OR (o.status='filled' AND o.filled_at > h.ts)
           OR (o.status='replaced' AND NOT EXISTS (SELECT 1 FROM mi_live_orders o2 WHERE o2.trade_id=o.trade_id AND o2.purpose='stop_loss' AND o2.submitted_at > o.submitted_at AND o2.submitted_at <= h.ts))
         ) AS is_live
  FROM held h JOIN mi_live_orders o ON o.trade_id=h.trade_id AND o.side ILIKE 'sell%' AND o.order_type ILIKE '%stop%' AND o.purpose='stop_loss' AND o.submitted_at <= h.ts
), per AS (
  SELECT h.d, h.nm, h.ticker, h.trade_id, coalesce(sum(l.qty) FILTER (WHERE l.is_live),0) AS live_stop_qty, count(*) FILTER (WHERE l.is_live) AS live_orders
  FROM held h LEFT JOIN liveord l ON l.d=h.d AND l.nm=h.nm AND l.trade_id=h.trade_id GROUP BY 1,2,3,4
)
SELECT nm, count(*) AS position_slots, count(*) FILTER (WHERE live_orders>0) AS mirror_shows_live_stop, count(*) FILTER (WHERE live_orders=0) AS mirror_shows_none
FROM per GROUP BY 1 ORDER BY 1;

WITH days AS (
  SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d) < 6
), slots AS (
  SELECT d, nm, ((d + t) AT TIME ZONE 'America/New_York') AS ts FROM days, (VALUES ('1700', time '17:00'),('1900', time '19:00'),('2110', time '21:10')) s(nm,t)
), held AS (
  SELECT s.d, s.nm, s.ts, t.id AS trade_id, t.ticker FROM slots s JOIN mi_live_trades t
    ON t.account_mode='live' AND t.filled_at IS NOT NULL AND t.filled_at < s.ts AND (t.closed_at IS NULL OR t.closed_at > s.ts)
), liveord AS (
  SELECT h.d, h.nm, h.ticker, h.trade_id, o.status, o.qty,
         ( o.status='new' OR (o.status IN ('canceled','cancelled') AND o.cancelled_at > h.ts) OR (o.status='filled' AND o.filled_at > h.ts)
           OR (o.status='replaced' AND NOT EXISTS (SELECT 1 FROM mi_live_orders o2 WHERE o2.trade_id=o.trade_id AND o2.purpose='stop_loss' AND o2.submitted_at > o.submitted_at AND o2.submitted_at <= h.ts))) AS is_live
  FROM held h JOIN mi_live_orders o ON o.trade_id=h.trade_id AND o.side ILIKE 'sell%' AND o.order_type ILIKE '%stop%' AND o.purpose='stop_loss' AND o.submitted_at <= h.ts
)
SELECT h.d, h.nm, h.ticker FROM held h
WHERE NOT EXISTS (SELECT 1 FROM liveord l WHERE l.d=h.d AND l.nm=h.nm AND l.trade_id=h.trade_id AND l.is_live)
ORDER BY h.d, h.nm, h.ticker;
