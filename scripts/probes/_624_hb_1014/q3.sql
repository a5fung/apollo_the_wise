\pset pager off
\echo === Q3-1 api_failure_fmp rows by ET day, last 8 days (is today's burst new, or the standing pattern?)
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD') d, count(*) n, min(to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI')) first_et, max(to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI')) last_et, count(DISTINCT left(summary,80)) distinct_msgs FROM mi_audit_log WHERE event_type='api_failure_fmp' AND created_at >= '2026-10-06 04:00+00' GROUP BY 1 ORDER BY 1;
\echo === Q3-2 api_failure_fmp today vs yesterday, same 16:00-22:30 UTC window, by endpoint text
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD') d, left(summary, 90) s, count(*) FROM mi_audit_log WHERE event_type='api_failure_fmp' AND created_at >= '2026-10-13 16:00+00' AND ((created_at < '2026-10-13 22:30+00') OR created_at >= '2026-10-14 16:00+00') GROUP BY 1,2 ORDER BY 1,2;
