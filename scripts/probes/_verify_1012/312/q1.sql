-- #312 Step A verify, Mon 2026-10-12. READ-ONLY.
\echo === A. unified_allocation_decided rows today (ET) ===
SELECT id, (created_at AT TIME ZONE 'America/New_York') AS et, summary, detail
FROM mi_audit_log
WHERE event_type = 'unified_allocation_decided'
  AND (created_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-12'
ORDER BY created_at;

\echo === B. mi_job_runs unified_allocator_shadow, last 4 days ===
SELECT job_id, status, (started_at AT TIME ZONE 'America/New_York') AS started_et, ROUND(duration_s*1000) AS ms, error
FROM mi_job_runs
WHERE job_id = 'unified_allocator_shadow' AND started_at > NOW() - INTERVAL '4 days'
ORDER BY started_at;

\echo === C. rebuilt 09:28 live book for 2026-10-12 ===
SELECT COUNT(*) AS rebuilt_0928 FROM mi_live_trades
WHERE account_mode = 'live' AND alert_date < DATE '2026-10-12'
  AND confirmed_at < (DATE '2026-10-12' + TIME '09:28') AT TIME ZONE 'America/New_York'
  AND (closed_at IS NULL OR closed_at >= (DATE '2026-10-12' + TIME '09:28') AT TIME ZONE 'America/New_York')
  AND status NOT IN ('cancelled', 'skipped');

\echo === C2. the rows in that book ===
SELECT id, ticker, account_mode, status, alert_date,
  (confirmed_at AT TIME ZONE 'America/New_York') AS confirmed_et,
  (closed_at AT TIME ZONE 'America/New_York') AS closed_et
FROM mi_live_trades
WHERE account_mode = 'live' AND alert_date < DATE '2026-10-12'
  AND confirmed_at < (DATE '2026-10-12' + TIME '09:28') AT TIME ZONE 'America/New_York'
  AND (closed_at IS NULL OR closed_at >= (DATE '2026-10-12' + TIME '09:28') AT TIME ZONE 'America/New_York')
  AND status NOT IN ('cancelled', 'skipped')
ORDER BY id;

\echo === D. pending allocations for today (columns) ===
SELECT * FROM mi_pending_allocations WHERE FALSE;
