SET default_transaction_read_only = on;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') t, event_type, left(detail::text,300) FROM mi_audit_log
 WHERE created_at > now() - interval '2 days' AND summary ILIKE '%Bitcoin Miners%' ORDER BY created_at;
SELECT table_name FROM information_schema.tables WHERE table_name ILIKE '%theme%' ORDER BY 1;
