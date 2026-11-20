SET default_transaction_read_only = on;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_job_runs';
SELECT * FROM mi_job_runs WHERE started_at > now() - interval '30 minutes' ORDER BY started_at;
SELECT event_type, created_at AT TIME ZONE 'America/New_York', left(detail::text,200) FROM mi_audit_log WHERE created_at > now() - interval '40 minutes' AND event_type NOT ILIKE 'exposure%' ORDER BY created_at;
