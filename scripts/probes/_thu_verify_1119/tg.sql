SET default_transaction_read_only = on;
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*), string_agg(DISTINCT split_part(detail::text,':',1), ',') FROM mi_audit_log WHERE event_type='telegram_send_failed' AND created_at > now()-interval '30 days' GROUP BY 1 ORDER BY 1;
