SET default_transaction_read_only = on;
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_ep_scan_log';
