\echo === B. mi_job_runs cols ===
SELECT * FROM mi_job_runs WHERE FALSE;
\echo === B2. unified_allocator_shadow runs last 5 days ===
SELECT job_id, status, (started_at AT TIME ZONE 'America/New_York') AS started_et, ROUND(duration_s*1000) AS ms
FROM mi_job_runs
WHERE job_id = 'unified_allocator_shadow' AND started_at > NOW() - INTERVAL '5 days'
ORDER BY started_at;
\echo === D. pending allocations created/alerted today or yesterday ===
SELECT id, ticker, alert_date, strategy, composite_score, status, shadow_rank, shadow_allocated,
  (created_at AT TIME ZONE 'America/New_York') AS created_et,
  (evaluated_at AT TIME ZONE 'America/New_York') AS evaluated_et
FROM mi_pending_allocations
WHERE alert_date >= DATE '2026-10-08' OR created_at > NOW() - INTERVAL '4 days'
ORDER BY created_at;
\echo === E. latest 5 audit allocator rows ===
SELECT id, (created_at AT TIME ZONE 'America/New_York') AS et, summary, LEFT(detail, 400) AS detail
FROM mi_audit_log WHERE event_type='unified_allocation_decided'
ORDER BY created_at DESC LIMIT 5;
\echo === F. EP scan activity today (mi_job_runs ep_scan*) ===
SELECT job_id, status, COUNT(*) n, MIN(started_at AT TIME ZONE 'America/New_York') first_et, MAX(started_at AT TIME ZONE 'America/New_York') last_et
FROM mi_job_runs
WHERE (started_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-12' AND job_id ILIKE '%ep%'
GROUP BY job_id, status ORDER BY job_id;
