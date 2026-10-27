SET default_transaction_read_only = on;
SELECT id, created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,220) FROM mi_audit_log WHERE created_at >= '2026-10-27 04:00-04' AND (summary ILIKE '%MFIC%' OR detail ILIKE '%"MFIC"%') ORDER BY id;
SELECT table_name FROM information_schema.tables WHERE table_name ILIKE 'mi_ep%' ORDER BY 1;
