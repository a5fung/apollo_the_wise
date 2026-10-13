-- #655 Tue 2026-10-13 night. READ-ONLY. schema peek + clock.
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et;
\echo == mi_job_runs columns
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_job_runs' ORDER BY ordinal_position;
\echo == mi_themes columns
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_themes' ORDER BY ordinal_position;
