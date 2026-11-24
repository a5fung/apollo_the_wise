SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York', event_type, left(summary,250) FROM mi_audit_log WHERE created_at >= '2026-11-21' AND (summary ILIKE '%Bitcoin Miners%' OR event_type ILIKE '%operator_exempt%' OR event_type ILIKE '%promot%' OR event_type ILIKE 'theme_sector_filter%') ORDER BY created_at;
