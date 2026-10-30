SET default_transaction_read_only = on;
\echo == audit
SELECT (created_at AT TIME ZONE 'America/New_York')::time(0) et, event_type, left(summary,300), left(coalesce(detail::text,''),900) FROM mi_audit_log WHERE event_type IN ('breakout_v1_list_run','breakout_v1_list_error') ORDER BY created_at DESC LIMIT 3;
\echo == list
SELECT scan_date, count(*) AS names, bool_and((gates->>'ok')::boolean) AS all_pass, string_agg(ticker || ':' || coalesce(security_type, '?') || ':' || round(rs_best::numeric,1), ' ' ORDER BY list_rank) AS list
FROM mi_breakout_v1_list GROUP BY scan_date ORDER BY scan_date DESC LIMIT 3;
\echo == names stored
SELECT count(*) FILTER (WHERE name IS NOT NULL) AS named, count(*) FROM mi_security_types;
\echo == job runs
SELECT job_id, status, (started_at AT TIME ZONE 'America/New_York')::time(0) et FROM mi_job_runs WHERE job_id IN ('breakout_v1_list','nightly_data_pull') AND started_at > '2026-10-30 16:00-04' ORDER BY started_at;
