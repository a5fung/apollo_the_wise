SET default_transaction_read_only = on;
SELECT now() AT TIME ZONE 'America/New_York' AS now_et;
SELECT * FROM mi_live_trades WHERE ticker IN ('ZYME','OUST','AMLX') AND alert_date >= '2026-11-09' ORDER BY id;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,300) AS summary
FROM mi_audit_log WHERE created_at >= '2026-11-10' AND (summary ILIKE '%ZYME%' OR detail::text ILIKE '%"ZYME"%') ORDER BY created_at;
