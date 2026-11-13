SET default_transaction_read_only = on;
SELECT event_type, created_at, left(summary,220) FROM mi_audit_log WHERE event_type LIKE 'drawdown%' AND created_at > now() - interval '30 days' ORDER BY created_at DESC LIMIT 12;
