-- #312 the first ladder_demotion_shadow row (the recovery re-run of Thu 10-15 16:17, date-pinned) — read-only
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, summary, left(detail::text, 3000) AS detail
  FROM mi_audit_log WHERE event_type = 'ladder_demotion_shadow' ORDER BY id;
SELECT job_id, status, started_at AT TIME ZONE 'America/New_York' AS et FROM mi_job_runs WHERE job_id='ladder_watchdog' ORDER BY started_at;
