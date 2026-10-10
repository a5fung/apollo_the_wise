SELECT ticker, trade_date, open_price, high_price, low_price, close, volume FROM mi_daily_closes
WHERE (ticker='GH' AND trade_date BETWEEN '2026-05-20' AND '2026-07-10')
   OR (ticker='HNGE' AND trade_date BETWEEN '2026-06-01' AND '2026-07-20')
   OR (ticker='CDNA' AND trade_date BETWEEN '2026-08-01' AND '2026-09-30')
ORDER BY ticker, trade_date;
