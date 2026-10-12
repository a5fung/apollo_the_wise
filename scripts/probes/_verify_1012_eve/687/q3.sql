\echo === COLS mi_ep_alerts
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_ep_alerts';
