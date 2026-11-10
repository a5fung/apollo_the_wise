SET default_transaction_read_only = on;
SELECT table_name, string_agg(column_name||':'||data_type, ', ' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name IN ('mi_daily_closes','mi_ep_catalyst_metrics') GROUP BY 1;
SELECT detail FROM mi_audit_log WHERE event_type='catalyst_earnings_revenue_weak_downgrade' ORDER BY id DESC LIMIT 1;
SELECT max(date) FROM mi_daily_closes;
