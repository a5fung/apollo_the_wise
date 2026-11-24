SET default_transaction_read_only = on;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') t, event_type, left(summary,170) FROM mi_audit_log WHERE created_at > now()-interval '8 days' AND (event_type LIKE 'theme_merge%' OR event_type LIKE 'theme_thesis%') ORDER BY created_at LIMIT 60;
