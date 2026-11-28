SET default_transaction_read_only = on;
SELECT trade_date, open_price, high_price, low_price, close, volume FROM mi_daily_closes WHERE ticker='GKOS' AND trade_date >= '2026-08-15' ORDER BY trade_date;
