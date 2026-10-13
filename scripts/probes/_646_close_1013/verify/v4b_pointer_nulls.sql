\pset pager off
\pset null '-'
-- V4b (re-issue of v4a/v4b, which errored on an ambiguous column): stop_order_id_changed timeline for LIVE trades 09-14..10-12 ET
WITH ch AS (
  SELECT a.id, a.created_at AS at, (a.detail::jsonb->>'trade_id')::int AS trade_id, a.detail::jsonb->>'account_mode' AS am,
         a.detail::jsonb->>'reason' AS reason, (a.detail::jsonb->>'new_id') IS NULL AS to_null
  FROM mi_audit_log a WHERE a.event_type='stop_order_id_changed' AND a.created_at >= '2026-09-14 04:00+00' AND a.created_at < '2026-10-13 12:00+00'
), ch2 AS (
  SELECT ch.*, lead(at) OVER w AS next_at, lead(reason) OVER w AS next_reason, lead(to_null) OVER w AS next_to_null
  FROM ch WINDOW w AS (PARTITION BY trade_id ORDER BY at, id)
)
SELECT ch2.am, ch2.reason, ch2.to_null, count(*) AS n,
       count(*) FILTER (WHERE ch2.to_null AND ch2.next_to_null = false) AS null_then_restored,
       count(*) FILTER (WHERE ch2.to_null AND ch2.next_at IS NULL) AS null_never_restored_in_window,
       max(extract(epoch FROM ch2.next_at - ch2.at)) FILTER (WHERE ch2.to_null) AS max_bare_s,
       string_agg(DISTINCT to_char(ch2.at AT TIME ZONE 'America/New_York','HH24:MI'),',') AS et_hhmm
FROM ch2 GROUP BY 1,2,3 ORDER BY 1,2,3;

WITH ch AS (
  SELECT a.id, a.created_at AS at, (a.detail::jsonb->>'trade_id')::int AS trade_id, a.detail::jsonb->>'account_mode' AS am,
         a.detail::jsonb->>'reason' AS reason, (a.detail::jsonb->>'new_id') IS NULL AS to_null
  FROM mi_audit_log a WHERE a.event_type='stop_order_id_changed' AND a.created_at >= '2026-09-14 04:00+00' AND a.created_at < '2026-10-13 12:00+00'
), ch2 AS (
  SELECT ch.*, lead(at) OVER w AS next_at, lead(reason) OVER w AS next_reason, lead(to_null) OVER w AS next_to_null
  FROM ch WINDOW w AS (PARTITION BY trade_id ORDER BY at, id)
)
SELECT to_char(ch2.at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS.MS') AS null_et, t.ticker, ch2.trade_id, ch2.reason,
       to_char(ch2.next_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS.MS') AS next_et, ch2.next_reason,
       round(extract(epoch FROM ch2.next_at - ch2.at)::numeric,2) AS bare_s
FROM ch2 LEFT JOIN mi_live_trades t ON t.id=ch2.trade_id
WHERE ch2.to_null AND ch2.am='live' AND (ch2.next_reason IS DISTINCT FROM 'stop_update_succeeded' OR extract(epoch FROM ch2.next_at - ch2.at) > 4)
ORDER BY ch2.at;

-- live NULL transitions per ET night between 16:00 and 21:10, and how many had the pointer back within 5 s
WITH ch AS (
  SELECT a.id, a.created_at AS at, (a.detail::jsonb->>'trade_id')::int AS trade_id, a.detail::jsonb->>'account_mode' AS am,
         a.detail::jsonb->>'reason' AS reason, (a.detail::jsonb->>'new_id') IS NULL AS to_null
  FROM mi_audit_log a WHERE a.event_type='stop_order_id_changed' AND a.created_at >= '2026-09-14 04:00+00' AND a.created_at < '2026-10-13 12:00+00'
), ch2 AS (
  SELECT ch.*, lead(at) OVER w AS next_at, lead(to_null) OVER w AS next_to_null
  FROM ch WINDOW w AS (PARTITION BY trade_id ORDER BY at, id)
)
SELECT count(*) AS live_nulls_16_to_2110,
       count(*) FILTER (WHERE next_to_null=false AND next_at - at <= interval '5 s') AS back_within_5s,
       count(*) FILTER (WHERE next_to_null=false AND next_at - at > interval '5 s') AS back_after_5s,
       count(*) FILTER (WHERE next_at IS NULL OR next_to_null) AS not_back
FROM ch2 WHERE am='live' AND to_null AND (at AT TIME ZONE 'America/New_York')::time BETWEEN '16:00' AND '21:10';
