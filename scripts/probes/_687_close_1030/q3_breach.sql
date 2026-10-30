SET default_transaction_read_only = on;
SELECT id, (created_at AT TIME ZONE 'America/New_York')::timestamp(0) et, event_type, summary, left(detail,900) detail FROM mi_audit_log
WHERE event_type = 'stop_breach_market_sale' AND created_at >= '2026-10-04';
