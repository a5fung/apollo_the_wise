SET default_transaction_read_only = on;
\echo == breakout list tonight
SELECT scan_date, count(*) AS names, min(adr20) AS min_adr20, sum((adr20 < 0.0426)::int) AS under_floor FROM mi_breakout_v1_list WHERE scan_date >= '2026-10-30' GROUP BY 1 ORDER BY 1;
\echo == breakout list audit tonight
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(detail::text, 700) FROM mi_audit_log WHERE created_at > NOW() - INTERVAL '3 hours' AND event_type ILIKE '%breakout_v1%' ORDER BY created_at DESC LIMIT 4;
\echo == 482 error rows since 17:00 ET
SELECT event_type, count(*), max(left(detail::text, 200)) FROM mi_audit_log WHERE created_at > (date_trunc('day', NOW() AT TIME ZONE 'America/New_York') + INTERVAL '17 hours') AT TIME ZONE 'America/New_York' AND event_type IN ('live_fill_counterfactual_error','book_geometry_arm_error') GROUP BY 1;
\echo == 482 recorder audit tonight
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(detail::text, 300) FROM mi_audit_log WHERE created_at > NOW() - INTERVAL '3 hours' AND (event_type ILIKE '%counterfactual%' OR event_type ILIKE '%book_geometry%') ORDER BY created_at DESC LIMIT 6;
\echo == 482 job runs tonight
SELECT job_id, started_at AT TIME ZONE 'America/New_York' AS et, status FROM mi_job_runs WHERE started_at > NOW() - INTERVAL '3 hours' AND (job_id ILIKE '%counterfactual%' OR job_id ILIKE '%geometry%' OR job_id ILIKE '%lfc%') ORDER BY started_at DESC LIMIT 6;
