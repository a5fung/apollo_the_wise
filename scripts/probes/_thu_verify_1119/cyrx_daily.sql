SET default_transaction_read_only = on;
SELECT trade_date, open_price, high_price, low_price, close FROM mi_daily_closes WHERE ticker='CYRX' AND trade_date BETWEEN '2026-11-16' AND '2026-11-18' ORDER BY 1;
SELECT id, ticker, account_mode, status, alert_date FROM mi_live_trades WHERE ticker='CAKE' ORDER BY id DESC LIMIT 3;
