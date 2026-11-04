SET default_transaction_read_only = on;

-- Q1: every capture row (and late-reason row) since 10-01. This is the DoD's audit-row evidence.
-- secs_after_submit tells a venue kill (seconds after submit) apart from our own cancel (10:00:0x cleanup, breakout minute job).
SELECT a.created_at AT TIME ZONE 'America/New_York' AS at_et,
       a.event_type,
       d.j->>'ticker' AS ticker, d.j->>'account_mode' AS mode, d.j->>'event_norm' AS ev,
       d.j->>'signal_type' AS sig,
       d.j->>'broker_reason' AS broker_reason, d.j->>'broker_reason_source' AS src,
       left(d.j->>'skip_reason', 80) AS skip_reason,
       ROUND(EXTRACT(EPOCH FROM (a.created_at - o.submitted_at))::numeric, 1) AS secs_after_submit
FROM mi_audit_log a
CROSS JOIN LATERAL (SELECT CASE WHEN a.detail LIKE '{%' THEN a.detail::jsonb END AS j) d
LEFT JOIN mi_live_orders o ON o.alpaca_order_id = d.j->>'order_id'
WHERE a.event_type IN ('entry_order_rejected', 'entry_order_reject_reason_late')
  AND a.created_at >= '2026-10-01 00:00 America/New_York'::timestamptz
ORDER BY a.created_at
LIMIT 40;

-- Q2: entries the broker killed according to the trade row (broker:* skip_reason), and whether the capture row exists.
-- has_capture_row=false means the polling path (check_fills, order_manager.py:1191) caught the kill first, so the capture never ran.
SELECT t.id, t.ticker, t.alert_date, t.account_mode, t.signal_type, t.status,
       left(t.skip_reason, 80) AS skip_reason,
       EXISTS (SELECT 1 FROM mi_audit_log a
               WHERE a.event_type = 'entry_order_rejected'
                 AND a.created_at >= '2026-10-01 00:00 America/New_York'::timestamptz
                 AND a.detail LIKE '%' || t.entry_order_id || '%') AS has_capture_row
FROM mi_live_trades t
WHERE t.alert_date >= DATE '2026-10-01'
  AND t.skip_reason LIKE 'broker:%'
ORDER BY t.alert_date, t.id
LIMIT 40;

-- Q3: exposure since the 10-21 check. Is the handler alive (heartbeat), and were any entries submitted that could have been rejected?
SELECT 'heartbeat' AS k, NULL::text AS mode, COUNT(*)::text AS n,
       MAX(created_at AT TIME ZONE 'America/New_York')::text AS latest
FROM mi_audit_log
WHERE event_type = 'entry_rejection_watch_armed'
  AND created_at >= '2026-10-21 00:00 America/New_York'::timestamptz
UNION ALL
SELECT 'trades:' || status, account_mode, COUNT(*)::text, MAX(alert_date)::text
FROM mi_live_trades
WHERE alert_date >= DATE '2026-10-21'
GROUP BY status, account_mode;