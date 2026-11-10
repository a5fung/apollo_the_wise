SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, detail::text FROM mi_audit_log
WHERE created_at >= '2026-11-10 20:55+00' AND (summary ILIKE '%ZYME%' OR detail::text ILIKE '%"ZYME"%' OR summary ILIKE '%AMLX%') ORDER BY created_at;
