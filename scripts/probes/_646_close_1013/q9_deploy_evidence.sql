\pset pager off
\pset null '-'
\pset format unaligned
\pset fieldsep ' | '
-- When did the repair-arm image first run? Look for boot/deploy/restart evidence 09-12..09-15 and the first coverage rows
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,160) AS summary
FROM mi_audit_log
WHERE created_at >= '2026-09-12' AND created_at < '2026-09-15 12:00+00'
  AND event_type ~* '(boot|startup|start_|deploy|restart|preflight|scheduler_started|job_recovery|git_sha|build)'
ORDER BY created_at LIMIT 40;
-- mi_job_runs 'interrupted' (process restart mid-run) in the same span
SELECT started_at AT TIME ZONE 'America/New_York' AS et, job_id, status, left(coalesce(error_message,''),120) AS err
FROM mi_job_runs WHERE started_at >= '2026-09-12' AND started_at < '2026-09-15 12:00+00' AND status<>'success' ORDER BY started_at;
