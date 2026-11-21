SET default_transaction_read_only = on;
\echo COT
SELECT event_type, created_at AT TIME ZONE 'America/New_York', jsonb_typeof(detail::jsonb) FROM mi_audit_log WHERE event_type ILIKE 'cot%' AND created_at > now()-interval '30 hours' ORDER BY created_at;
\echo JOBS
SELECT job_id, status, started_at AT TIME ZONE 'America/New_York' FROM mi_job_runs WHERE job_id ILIKE 'cot%' AND started_at > now()-interval '30 hours';
\echo BREAKOUT_PARTIAL
SELECT event_type, created_at AT TIME ZONE 'America/New_York', left(detail::text,200) FROM mi_audit_log WHERE created_at > now()-interval '20 hours' AND (event_type ILIKE 'breakout_pp%' OR event_type ILIKE 'stop_update%' OR event_type ILIKE 'naked%' OR event_type ILIKE 'profit_trigger%' OR event_type ILIKE 'telegram_send%');
