SET default_transaction_read_only = on;
SELECT table_name, column_name FROM information_schema.columns WHERE column_name ILIKE '%regime%' AND table_name IN ('mi_ep_alerts','mi_live_trades','mi_sell_discipline_records','mi_market_regime','mi_regime_history') ORDER BY 1;
SELECT table_name FROM information_schema.tables WHERE table_name ILIKE '%regime%' ORDER BY 1;
