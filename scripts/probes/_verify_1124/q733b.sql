SET default_transaction_read_only = on;
SELECT stop_reason, model, count(*) FROM api_usage WHERE caller LIKE 'theme_merge%' AND created_at >= '2026-11-24 00:00-05' GROUP BY 1,2;
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York') FROM mi_audit_log WHERE event_type LIKE 'theme_merge%' AND created_at >= '2026-11-24 00:00-05' GROUP BY 1;
SELECT created_at AT TIME ZONE 'America/New_York', event_type, left(summary,180), left(detail::text,300) FROM mi_audit_log WHERE event_type LIKE 'theme_merge%' AND created_at >= '2026-11-24 00:00-05' ORDER BY created_at;
SELECT job_name, status, started_at AT TIME ZONE 'America/New_York' FROM mi_job_runs WHERE started_at >= '2026-11-24 16:30-05' ORDER BY started_at;
