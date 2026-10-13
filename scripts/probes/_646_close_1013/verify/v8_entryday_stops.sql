\pset pager off
\pset null '-'
-- V8: entry-day stop legs — mirror stop_price vs the broker's own raw_response stop_price, for the 4 DAY expiries and two
-- same-day stop-outs (DFTX 399, PHVS 394) as a comparison; plus order class / legs fields
SELECT t.ticker, o.trade_id, left(o.alpaca_order_id,8) AS oid, o.status, o.stop_price AS mirror_stop,
       o.raw_response->>'stop_price' AS raw_stop, o.raw_response->>'order_class' AS cls, o.raw_response->>'type' AS typ,
       o.raw_response->>'time_in_force' AS tif, t.orb_low, t.hard_stop, t.entry_price,
       to_char(o.submitted_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS sub_et,
       to_char(coalesce(o.cancelled_at,o.filled_at) AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS end_et,
       left(o.raw_response::text, 160) AS raw_head
FROM mi_live_orders o JOIN mi_live_trades t ON t.id=o.trade_id
WHERE o.trade_id IN (400,409,414,419,399,394) AND o.purpose='stop_loss'
  AND (o.submitted_at AT TIME ZONE 'America/New_York')::date = (t.filled_at AT TIME ZONE 'America/New_York')::date
ORDER BY o.trade_id, o.submitted_at;
