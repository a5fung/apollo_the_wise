\echo === COLS mi_live_trades
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_live_trades';
\echo === COLS mi_safeguard_state
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_safeguard_state';
\echo === COLS mi_audit_log
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_audit_log';
\echo === COLS mi_job_runs
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_job_runs';
\echo === COLS mi_live_orders
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_live_orders';
\echo === NOW
SELECT now() AT TIME ZONE 'America/New_York';
