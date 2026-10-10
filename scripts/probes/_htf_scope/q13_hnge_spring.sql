SELECT trade_date, low_price, close FROM mi_daily_closes WHERE ticker='HNGE' AND trade_date BETWEEN '2026-03-01' AND '2026-06-01' ORDER BY trade_date;
