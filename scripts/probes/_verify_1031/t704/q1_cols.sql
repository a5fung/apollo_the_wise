SET default_transaction_read_only = on;
SELECT table_name, column_name, data_type FROM information_schema.columns
 WHERE table_name IN ('mi_splits') ORDER BY ordinal_position;
SELECT table_name, column_name FROM information_schema.columns
 WHERE table_name IN ('mi_audit_log','mi_daily_closes') ORDER BY table_name, ordinal_position;
