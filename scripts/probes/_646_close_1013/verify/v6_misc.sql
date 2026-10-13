\pset pager off
\pset null '-'
-- V6a: calendar sanity
SELECT d::date, to_char(d,'Dy') FROM generate_series('2026-09-14'::date,'2026-09-15'::date,'1 day') d
UNION ALL SELECT '2026-10-12'::date, to_char('2026-10-12'::date,'Dy');
-- V6b: first-ever / all runs of the coverage + backstop jobs, all statuses, all time
SELECT job_id, min(started_at AT TIME ZONE 'America/New_York') AS first_run_et, max(started_at AT TIME ZONE 'America/New_York') AS last_run_et,
       count(*) AS runs, string_agg(DISTINCT status, ',') AS statuses
FROM mi_job_runs WHERE job_id IN ('coverage_watch_post_close','coverage_watch_late','coverage_watch_evening','evening_coverage_verify','evening_position_backstop')
GROUP BY 1 ORDER BY 1;
-- V6c: 16:45 cycle — stop_updated price direction + retry rows per night (live trades only)
SELECT count(*) AS stop_updated_rows,
       count(*) FILTER (WHERE (detail::jsonb->>'new_stop_price')::numeric < (detail::jsonb->>'old_stop_price')::numeric) AS new_below_old,
       count(*) FILTER (WHERE (detail::jsonb->>'new_stop_price')::numeric >= (detail::jsonb->>'old_stop_price')::numeric) AS new_ge_old,
       count(*) FILTER (WHERE detail::jsonb->>'old_stop_price' IS NULL) AS old_null,
       string_agg(DISTINCT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI'),',') AS hhmm
FROM mi_audit_log WHERE event_type='stop_updated' AND created_at >= '2026-09-14 04:00+00' AND created_at < '2026-10-13 12:00+00';
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS et, detail::jsonb->>'ticker' AS tkr,
       detail::jsonb->>'old_stop_price' AS old_p, detail::jsonb->>'new_stop_price' AS new_p, detail::jsonb->>'effective_qty' AS q
FROM mi_audit_log WHERE event_type='stop_updated' AND created_at >= '2026-09-14 04:00+00' AND created_at < '2026-10-13 12:00+00'
  AND ((detail::jsonb->>'new_stop_price')::numeric < (detail::jsonb->>'old_stop_price')::numeric OR (created_at AT TIME ZONE 'America/New_York')::time < '16:30')
ORDER BY created_at;
SELECT count(*) FILTER (WHERE event_type='stop_update_retry_triggered') AS retry_trig,
       count(*) FILTER (WHERE event_type='stop_update_retry_succeeded') AS retry_ok,
       count(*) FILTER (WHERE event_type='stop_update_started' AND (created_at AT TIME ZONE 'America/New_York')::time BETWEEN '16:44' AND '16:50') AS started_1645,
       count(*) FILTER (WHERE event_type='stop_update_failed') AS failed
FROM mi_audit_log WHERE created_at >= '2026-09-14 04:00+00' AND created_at < '2026-10-13 12:00+00';
-- V6d: current pointers on the still-open live trades vs the 16:20 refresh order ids
SELECT t.id, t.ticker, left(t.stop_order_id,8) AS ptr_now, o.status AS ptr_order_status, o.stop_price AS ptr_stop_price,
       to_char(o.submitted_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS ptr_sub_et
FROM mi_live_trades t LEFT JOIN mi_live_orders o ON o.alpaca_order_id=t.stop_order_id
WHERE t.account_mode='live' AND t.status='filled';
-- V6e: any audit row ever about untracked/unknown broker positions in the window
SELECT event_type, count(*) FROM mi_audit_log
WHERE created_at >= '2026-09-14 04:00+00' AND created_at < '2026-10-13 12:00+00'
  AND event_type ~* '(untracked|unknown_pos|orphan_pos|position_mismatch|qty_mismatch|sync_qty|broker_only|flat)'
GROUP BY 1 ORDER BY 1;
