SET default_transaction_read_only = on;
SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND (table_name ILIKE '%telegram%' OR table_name ILIKE '%message%' OR table_name ILIKE '%notif%' OR table_name ILIKE '%outbox%' OR table_name ILIKE '%sent%');
SELECT column_name FROM information_schema.columns WHERE table_name='mi_audit_log' ORDER BY ordinal_position;
