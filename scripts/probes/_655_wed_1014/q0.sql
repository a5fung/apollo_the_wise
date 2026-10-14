-- #655 Wed 2026-10-14 night (night 3 of 5 for the G3 fold DONE-WHEN). READ-ONLY. q0 = clock, deploy-boot evidence, job runs.
\pset format unaligned
\pset fieldsep '\t'
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et;
\echo == A. audit events 11:55-12:30 ET today (boot / deploy evidence)
SELECT event_type, count(*) n, min((created_at AT TIME ZONE 'America/New_York')::time(0))::text first_t, max((created_at AT TIME ZONE 'America/New_York')::time(0))::text last_t
FROM mi_audit_log WHERE created_at >= '2026-10-14 11:55:00-04' AND created_at < '2026-10-14 12:30:00-04' GROUP BY 1 ORDER BY 3,1;
\echo == B. job runs today since 16:00 ET (all jobs)
SELECT id, job_id, (started_at AT TIME ZONE 'America/New_York')::time(0)::text st, status, rows_written, left(coalesce(error_message,''),160) err
FROM mi_job_runs WHERE started_at >= '2026-10-14 16:00:00-04' ORDER BY id;
\echo == C. any failed/errored job runs today since 12:00 ET
SELECT id, job_id, (started_at AT TIME ZONE 'America/New_York')::time(0)::text st, status, left(coalesce(error_message,''),200) err
FROM mi_job_runs WHERE started_at >= '2026-10-14 12:00:00-04' AND status <> 'success' ORDER BY id;
\echo == D. theme-lane heartbeat / rank / flag-scan style events since 17:00 ET
SELECT event_type, count(*) n, min((created_at AT TIME ZONE 'America/New_York')::time(0))::text first_t, max((created_at AT TIME ZONE 'America/New_York')::time(0))::text last_t
FROM mi_audit_log WHERE created_at >= '2026-10-14 17:00:00-04' AND (event_type ILIKE '%heartbeat%' OR event_type ILIKE '%rank%' OR event_type ILIKE '%flag%' OR event_type ILIKE '%lane%') GROUP BY 1 ORDER BY 3,1;
