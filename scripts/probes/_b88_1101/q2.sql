SET default_transaction_read_only = on;
\copy (SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, summary, detail::text AS detail FROM mi_audit_log WHERE event_type = 'mna_filter_fired' AND created_at >= NOW() - INTERVAL '30 days' ORDER BY created_at) TO STDOUT WITH CSV HEADER
