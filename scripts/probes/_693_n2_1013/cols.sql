\echo == api_usage cols
SELECT column_name FROM information_schema.columns WHERE table_name='api_usage' ORDER BY ordinal_position;
\echo == mi_job_runs cols
SELECT column_name FROM information_schema.columns WHERE table_name='mi_job_runs' ORDER BY ordinal_position;
\echo == mi_audit_log cols
SELECT column_name FROM information_schema.columns WHERE table_name='mi_audit_log' ORDER BY ordinal_position;
\echo == now
SELECT now() AT TIME ZONE 'America/New_York' now_et;
