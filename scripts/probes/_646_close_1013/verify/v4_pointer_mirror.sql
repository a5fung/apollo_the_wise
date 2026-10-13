\pset pager off
\pset null '-'
-- V4a: every stop_order_id_changed row for a LIVE trade, 09-14 .. 10-12 (ET), with the NEXT change on the same trade.
WITH ch AS (
  SELECT id, created_at, (detail::jsonb->>'trade_id')::int AS trade_id, detail::jsonb->>'account_mode' AS am,
         detail::jsonb->>'reason' AS reason, (detail::jsonb->>'new_id') IS NULL AS to_null
  FROM mi_audit_log WHERE event_type='stop_order_id_changed' AND created_at >= '2026-09-14 04:00+00' AND created_at < '2026-10-13 12:00+00'
), ch2 AS (
  SELECT ch.*, lead(created_at) OVER w AS next_at, lead(reason) OVER w AS next_reason, lead(to_null) OVER w AS next_to_null
  FROM ch WINDOW w AS (PARTITION BY trade_id ORDER BY created_at, id)
)
SELECT ch2.am, t.ticker, ch2.trade_id, reason, to_null, count(*) AS n,
       count(*) FILTER (WHERE to_null AND next_to_null = false) AS null_then_restored,
       max(extract(epoch FROM next_at - created_at)) FILTER (WHERE to_null) AS max_bare_s,
       string_agg(DISTINCT to_char(created_at AT TIME ZONE 'America/New_York','HH24'),',') AS et_hours
FROM ch2 LEFT JOIN mi_live_trades t ON t.id=ch2.trade_id
GROUP BY 1,2,3,4,5 ORDER BY 1,3,4,5;

-- V4b: every NULL transition on a LIVE trade with its next change (row level)
WITH ch AS (
  SELECT id, created_at, (detail::jsonb->>'trade_id')::int AS trade_id, detail::jsonb->>'account_mode' AS am,
         detail::jsonb->>'reason' AS reason, (detail::jsonb->>'new_id') IS NULL AS to_null
  FROM mi_audit_log WHERE event_type='stop_order_id_changed' AND created_at >= '2026-09-14 04:00+00' AND created_at < '2026-10-13 12:00+00'
), ch2 AS (
  SELECT ch.*, lead(created_at) OVER w AS next_at, lead(reason) OVER w AS next_reason, lead(to_null) OVER w AS next_to_null
  FROM ch WINDOW w AS (PARTITION BY trade_id ORDER BY created_at, id)
)
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS.MS') AS null_et, t.ticker, trade_id, reason,
       to_char(next_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS.MS') AS next_et, next_reason, next_to_null,
       round(extract(epoch FROM next_at - created_at)::numeric,2) AS bare_s
FROM ch2 LEFT JOIN mi_live_trades t ON t.id=ch2.trade_id
WHERE to_null AND am='live' ORDER BY created_at;

-- V4c: stop_refresh_ran rows in window that placed anything or listed unprotected
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS et, detail::jsonb->>'pass' AS pass,
       detail::jsonb->>'examined' AS ex, detail::jsonb->>'placed' AS placed, detail::jsonb->'placed_tickers' AS placed_t,
       detail::jsonb->'already_covered' AS covered_t, detail::jsonb->'unprotected' AS unprot, detail::jsonb->'skipped' AS skipped
FROM mi_audit_log WHERE event_type='stop_refresh_ran' AND created_at >= '2026-09-14 04:00+00' AND created_at < '2026-10-13 12:00+00'
  AND ((detail::jsonb->>'placed')::int > 0 OR jsonb_array_length(detail::jsonb->'unprotected') > 0 OR jsonb_array_length(detail::jsonb->'skipped') > 0)
ORDER BY created_at;

-- V4d: order mirror vocabulary for LIVE trades' sell orders since 09-12
SELECT o.purpose, o.order_type, o.status, o.raw_response->>'time_in_force' AS tif, count(*) AS n,
       count(*) FILTER (WHERE o.cancelled_at IS NOT NULL) AS has_cancelled_at
FROM mi_live_orders o JOIN mi_live_trades t ON t.id=o.trade_id
WHERE t.account_mode='live' AND o.submitted_at >= '2026-09-10' AND o.side ILIKE '%sell%'
GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;

-- V4e: the four entry-day stop orders (VICR 400 / CEG 409 / PENG 414 / HUM 419): every sell stop row on those trades
-- submitted on the entry day or the evening after, with lifecycle columns
SELECT t.ticker, o.trade_id, left(o.alpaca_order_id,8) AS oid, o.purpose, o.order_type, o.qty, o.stop_price, o.status,
       o.raw_response->>'time_in_force' AS tif,
       to_char(o.submitted_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS sub_et,
       to_char(o.cancelled_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS canc_et,
       to_char(o.filled_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS fill_et
FROM mi_live_orders o JOIN mi_live_trades t ON t.id=o.trade_id
WHERE o.trade_id IN (400,409,414,419) AND o.side ILIKE '%sell%'
  AND (o.submitted_at AT TIME ZONE 'America/New_York')::date <= (t.filled_at AT TIME ZONE 'America/New_York')::date + 1
ORDER BY o.trade_id, o.submitted_at;
