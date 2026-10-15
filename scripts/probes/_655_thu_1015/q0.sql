-- #655 Thu 2026-10-15 night (night 4; fold DONE-WHEN already met 10-14). READ-ONLY. q0 = clock + job runs + theme audit events since 16:30 ET Thu.
\pset format unaligned
\pset fieldsep '\t'
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et;
\echo == A. non-success job runs since 12:00 ET today
SELECT id, job_id, (started_at AT TIME ZONE 'America/New_York')::time(0)::text st, status, left(coalesce(error_message,''),200) err
FROM mi_job_runs WHERE started_at >= '2026-10-15 12:00:00-04' AND status <> 'success' ORDER BY id;
\echo == B. the night's key jobs (audit 17:30, flag scan 17:25, rank 17:53, lane heartbeat 18:15, data pull)
SELECT id, job_id, (started_at AT TIME ZONE 'America/New_York')::time(0)::text st, status, rows_written
FROM mi_job_runs WHERE started_at >= '2026-10-15 16:30:00-04' AND job_id IN ('nightly_data_pull','flag_continuation_scan','post_nightly_audit','alert_rank_shadow','lowcap_lane_replay','theme_synthesis','theme_axis_bounded_sweep') ORDER BY id;
\echo == C. theme audit events since 16:30 ET Thu (counts)
SELECT event_type, count(*) n, min((created_at AT TIME ZONE 'America/New_York')::time(0))::text first_t, max((created_at AT TIME ZONE 'America/New_York')::time(0))::text last_t
FROM mi_audit_log WHERE created_at >= '2026-10-15 16:30:00-04' AND (event_type LIKE 'theme%' OR event_type LIKE '%fold%' OR event_type LIKE 'validation_mass%')
GROUP BY 1 ORDER BY 3,1;
\echo == D. lane heartbeat / rank / flag events since 17:00 ET
SELECT event_type, count(*) n, min((created_at AT TIME ZONE 'America/New_York')::time(0))::text first_t, max((created_at AT TIME ZONE 'America/New_York')::time(0))::text last_t
FROM mi_audit_log WHERE created_at >= '2026-10-15 17:00:00-04' AND (event_type ILIKE '%heartbeat%' OR event_type ILIKE '%rank%' OR event_type ILIKE '%flag%' OR event_type ILIKE '%lane%') GROUP BY 1 ORDER BY 3,1;
