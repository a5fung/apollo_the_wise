SET default_transaction_read_only = on;
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, summary FROM mi_audit_log
 WHERE created_at > now() - interval '3 days' AND summary ILIKE '%Bitcoin Miners%' ORDER BY created_at;
