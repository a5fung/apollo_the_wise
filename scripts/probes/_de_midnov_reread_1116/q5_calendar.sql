SET default_transaction_read_only = on;
SELECT trade_date, COUNT(*) FROM mi_daily_closes WHERE trade_date >= DATE '2026-08-01' GROUP BY 1 ORDER BY 1;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_market_regime' ORDER BY ordinal_position;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_delayed_entry_watch' ORDER BY ordinal_position;
