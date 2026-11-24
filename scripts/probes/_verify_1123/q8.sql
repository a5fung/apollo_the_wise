SET default_transaction_read_only = on;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') t, event_type, left(summary,220) FROM mi_audit_log WHERE created_at >= '2026-11-22 17:00-05' AND (summary ILIKE '%dead-column%' OR event_type ILIKE 'dead_column%') ORDER BY created_at;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') t, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-11-23 15:00-05' AND (summary ILIKE '%trail%' OR summary ILIKE '%breakeven%' OR event_type ILIKE '%update_open_positions%') ORDER BY created_at LIMIT 10;
