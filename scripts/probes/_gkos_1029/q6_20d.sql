SET default_transaction_read_only = on;
SELECT alert_date, ticker, source, skip_category, ret_5d, ret_20d, max_high_20d FROM mi_ep_missed_outcomes WHERE alert_date='2026-10-29' AND ticker='GKOS';
SELECT trade_date, open_price, high, low, close, volume FROM mi_daily_closes WHERE ticker='GKOS' AND trade_date >= '2026-10-29' ORDER BY trade_date;
