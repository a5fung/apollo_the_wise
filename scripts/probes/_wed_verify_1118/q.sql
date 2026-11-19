SET default_transaction_read_only = on;
SELECT id, created_at AT TIME ZONE 'America/New_York' et, jsonb_typeof(detail) FROM mi_cot_alerts ORDER BY id DESC LIMIT 6;
SELECT s.ticker, s.entry_mode, s.is_common_stock, s.created_at AT TIME ZONE 'America/New_York' et FROM mi_consolidation_entry_shadow s WHERE s.created_at > now() - interval '6 hours' ORDER BY 1;
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(detail::text,300) FROM mi_audit_log WHERE created_at > now() - interval '6 hours' AND (event_type ILIKE '%consolidation_readiness%' OR event_type ILIKE '%family_a%' OR event_type ILIKE '%anticipation%') ORDER BY created_at DESC LIMIT 8;
SELECT run_at AT TIME ZONE 'America/New_York', status FROM mi_job_runs WHERE job_name ILIKE '%consolidation_readiness%' ORDER BY run_at DESC LIMIT 2;
