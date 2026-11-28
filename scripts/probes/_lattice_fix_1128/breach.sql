SET default_transaction_read_only = on;
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n, left(min(summary),140)
FROM mi_audit_log WHERE event_type='ep_candidate_parse_error' AND created_at >= '2026-08-01' GROUP BY 1 ORDER BY 1;
