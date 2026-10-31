SET default_transaction_read_only = on;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_live_trades'
AND (column_name ~ '(^r_|_r$|_r_|peak|mfe|mae|realized|pnl|exit|stop|entry_price|risk|status|signal|account|alert_date|close|regime|exit_rule|partial)') ORDER BY ordinal_position;
