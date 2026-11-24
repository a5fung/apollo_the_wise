SET default_transaction_read_only = on;
SELECT count(DISTINCT as_of_date) days, min(as_of_date), max(as_of_date) FROM mi_analyst_estimates;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') t, event_type, left(summary,200) FROM mi_audit_log WHERE event_type ILIKE '%durab%' OR event_type ILIKE '%step0%' OR event_type ILIKE '%analyst_estimates_60d%' ORDER BY created_at DESC LIMIT 10;
