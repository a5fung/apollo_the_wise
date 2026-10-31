SET default_transaction_read_only = on;
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York')::date AS first_et, max(created_at AT TIME ZONE 'America/New_York')::date AS last_et
FROM mi_audit_log WHERE created_at >= '2026-10-17' AND (event_type ILIKE '%promot%' OR event_type ILIKE '%pass1_5%') GROUP BY 1 ORDER BY 1;
