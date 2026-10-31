SET default_transaction_read_only = on;
SELECT table_name, column_name FROM information_schema.columns WHERE table_name IN ('mi_live_trades','mi_ep_alerts') ORDER BY table_name, ordinal_position;
