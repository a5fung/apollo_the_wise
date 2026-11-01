SET default_transaction_read_only = on;
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, summary, LEFT(detail::text, 400) FROM mi_audit_log WHERE event_type = 'anomaly_detected' AND summary LIKE 'L2%' AND created_at >= NOW() - INTERVAL '90 days' ORDER BY summary, created_at;
