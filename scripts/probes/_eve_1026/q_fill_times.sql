SET default_transaction_read_only = on;
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_live_trades' AND (column_name LIKE '%fill%' OR column_name LIKE '%entry%time%' OR column_name LIKE '%entered%' OR column_name='id');
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at >= '2026-10-26 12:50-04' AND (event_type ILIKE '%dead%col%' OR detail ILIKE '%fill_vs_trigger%' OR detail ILIKE '%real_risk%' OR detail ILIKE '%sizing_risk_pct%') GROUP BY 1;
