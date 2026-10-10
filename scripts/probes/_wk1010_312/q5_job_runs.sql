-- #312 Step A fix round (finding 4): run-time of the allocator job in mi_job_runs. READ-ONLY.
SELECT job_id, status, COUNT(*) AS runs,
       ROUND(MIN(duration_s) * 1000) AS min_ms, ROUND(MAX(duration_s) * 1000) AS max_ms,
       MIN(started_at AT TIME ZONE 'America/New_York') AS first_et,
       MAX(started_at AT TIME ZONE 'America/New_York') AS last_et
FROM mi_job_runs
WHERE job_id = 'unified_allocator_shadow' AND started_at > NOW() - INTERVAL '60 days'
GROUP BY job_id, status ORDER BY status;
