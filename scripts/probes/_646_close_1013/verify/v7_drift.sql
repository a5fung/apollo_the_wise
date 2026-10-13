\pset pager off
\pset null '-'
-- V7: what the coverage_drift_* rows in the window are (gatherer called them a data-coverage check; task_closes.md calls coverage_drift the ORDER-MIRROR drift detector)
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS et, event_type, left(summary,230) AS summary, left(detail,400) AS detail
FROM mi_audit_log
WHERE event_type ~ '^coverage_drift' AND created_at >= '2026-09-14 04:00+00' AND created_at < '2026-10-13 12:00+00'
ORDER BY created_at;
