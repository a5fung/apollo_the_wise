\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
SELECT '10_ep_scan_jobs' AS chk, (scheduled_for AT TIME ZONE 'America/New_York')::date AS d, job_id, status, count(*) FROM mi_job_runs WHERE scheduled_for >= TIMESTAMPTZ '2026-10-12 00:00-04' AND (job_id ILIKE '%ep_scan%' OR job_id ILIKE '%ep_detect%' OR job_id ILIKE '%ep_alert%' OR job_id ILIKE '%premarket_ep%') GROUP BY 2,3,4 ORDER BY 2,3,4;
SELECT '11_ep_audit' AS chk, (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type, count(*) FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-10-12 00:00-04' AND (event_type ILIKE 'ep_%' OR event_type ILIKE '%ep_scan%') GROUP BY 2,3 ORDER BY 2,3 LIMIT 30;
