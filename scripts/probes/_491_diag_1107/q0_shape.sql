SET default_transaction_read_only = on;
SELECT detail FROM mi_audit_log WHERE event_type='promote_member_skipped' ORDER BY created_at DESC LIMIT 2;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_validation_cooldowns' ORDER BY ordinal_position;
