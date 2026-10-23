\pset pager off
SELECT table_name, string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name IN ('mi_live_trades','mi_ep_alerts','mi_job_runs','mi_ep_scan_log','mi_audit_log','mi_runtime_toggles') GROUP BY 1;
SELECT table_name FROM information_schema.tables WHERE table_name ILIKE '%toggle%' OR table_name ILIKE '%safeguard%';
