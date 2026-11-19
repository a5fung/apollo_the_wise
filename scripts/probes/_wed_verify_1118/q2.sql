SET default_transaction_read_only = on;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_job_runs';
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(detail::text,400) FROM mi_audit_log WHERE created_at > now() - interval '8 hours' AND event_type ILIKE '%cot%' ORDER BY created_at DESC LIMIT 8;
SELECT ticker, entry_mode, is_common_stock, outcome, created_at::date FROM mi_consolidation_entry_shadow WHERE ticker IN ('FNGD','ZCSH') ORDER BY created_at DESC LIMIT 5;
