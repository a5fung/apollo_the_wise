\pset pager off
\pset null '-'
-- (a) mirror vocabulary: live-account sell orders since 09-10
SELECT o.purpose, o.order_type, o.status, count(*) AS n, count(*) FILTER (WHERE o.cancelled_at IS NULL) AS cancelled_at_null, count(*) FILTER (WHERE o.filled_at IS NULL) AS filled_at_null
FROM mi_live_orders o JOIN mi_live_trades t ON t.id=o.trade_id
WHERE t.account_mode='live' AND o.submitted_at >= '2026-09-10' AND o.side ILIKE 'sell%'
GROUP BY 1,2,3 ORDER BY 1,2,3;

-- (b) do the paper-rehearsal trade ids named in the audit rows still exist? (ids 399..425, any mode/status)
SELECT id, ticker, account_mode, status, alert_date, filled_at AT TIME ZONE 'America/New_York' AS filled_et, closed_at AT TIME ZONE 'America/New_York' AS closed_et, remaining_shares
FROM mi_live_trades WHERE id BETWEEN 399 AND 425 ORDER BY id;

-- (c) live closed-trade exit records in window (how each live position actually ended)
SELECT id, ticker, status, closed_at AT TIME ZONE 'America/New_York' AS closed_et, left(exits::text, 300) AS exits
FROM mi_live_trades WHERE account_mode='live' AND closed_at >= '2026-09-14' ORDER BY closed_at;

-- (d) after-16:00 ET context rows: broker/api failures, recovery sweeps, reconcile, mgmt judge, stop_refresh_ran
\pset format unaligned
\pset fieldsep ' | '
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,250) AS summary, left(detail,400) AS detail
FROM mi_audit_log
WHERE created_at >= '2026-09-14' AND created_at < '2026-10-13 12:00+00'
  AND (created_at AT TIME ZONE 'America/New_York')::time BETWEEN '16:00' AND '21:30'
  AND extract(isodow FROM created_at AT TIME ZONE 'America/New_York') < 6
  AND event_type IN ('api_failure_alpaca','coverage_drift_check_degraded','job_recovery_sweep','order_status_reconciled','position_mgmt_judge_null')
ORDER BY created_at;
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, left(summary,200) AS summary, left(detail,300) AS detail
FROM mi_audit_log WHERE event_type='stop_refresh_ran' AND created_at >= '2026-09-14' AND created_at < '2026-10-13 12:00+00'
  AND (created_at AT TIME ZONE 'America/New_York')::time > '16:00' ORDER BY created_at;
\pset format aligned

-- (e) for each LIVE trade NULL-ing event, the next non-null stop_order_id_changed for the same trade: gap seconds (NULL = none in audit)
WITH ev AS (
  SELECT id, created_at, (detail::jsonb->>'trade_id')::int AS trade_id, detail::jsonb->>'new_id' AS new_id, detail::jsonb->>'reason' AS reason, detail::jsonb->>'account_mode' AS mode
  FROM mi_audit_log WHERE event_type='stop_order_id_changed' AND created_at >= '2026-09-12' AND created_at < '2026-10-13 14:00+00'
)
SELECT n.id, n.created_at AT TIME ZONE 'America/New_York' AS null_et, n.trade_id, n.reason,
       (SELECT extract(epoch FROM (e2.created_at - n.created_at))::numeric(10,1) FROM ev e2 WHERE e2.trade_id=n.trade_id AND e2.new_id IS NOT NULL AND e2.created_at > n.created_at ORDER BY e2.created_at LIMIT 1) AS secs_to_next_nonnull,
       (SELECT e2.reason FROM ev e2 WHERE e2.trade_id=n.trade_id AND e2.new_id IS NOT NULL AND e2.created_at > n.created_at ORDER BY e2.created_at LIMIT 1) AS next_reason,
       (SELECT t.status FROM mi_live_trades t WHERE t.id=n.trade_id) AS trade_status_now
FROM ev n WHERE n.new_id IS NULL AND n.mode='live'
ORDER BY n.created_at;
