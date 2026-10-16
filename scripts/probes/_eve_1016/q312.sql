-- READ-ONLY. #312 ladder watchdog: the first SCHEDULED run (Fri 10-16 16:17 ET) — the row and the job ledger.
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, summary, detail FROM mi_audit_log WHERE event_type='ladder_demotion_shadow' ORDER BY id DESC LIMIT 3;
SELECT started_at AT TIME ZONE 'America/New_York' AS et, status, round(duration_s,1) s FROM mi_job_runs WHERE job_id ILIKE '%ladder%' ORDER BY started_at DESC LIMIT 4;
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at >= '2026-10-16 20:00+00' AND (event_type ILIKE '%ladder%' OR summary ILIKE '%ladder%') GROUP BY 1;
