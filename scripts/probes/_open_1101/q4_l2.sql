SET default_transaction_read_only = on;
SELECT COUNT(*) FROM mi_audit_log WHERE event_type = 'anomaly_detected' AND summary LIKE 'L2%' AND created_at >= NOW() - INTERVAL '90 days';
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, LEFT(summary, 200) AS summary FROM mi_audit_log WHERE event_type = 'anomaly_detected' AND summary LIKE 'L2%' AND created_at >= NOW() - INTERVAL '90 days' ORDER BY created_at;
