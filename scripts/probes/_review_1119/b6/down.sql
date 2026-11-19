SET default_transaction_read_only = on;
SELECT created_at::date, detail FROM mi_audit_log WHERE event_type='catalyst_earnings_revenue_weak_downgrade' AND created_at >= '2026-10-20' ORDER BY created_at DESC LIMIT 4;
