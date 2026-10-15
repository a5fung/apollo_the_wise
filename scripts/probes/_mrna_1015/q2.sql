-- MRNA daily bars 09-10..09-18 (read-only): is 9/16 an inside day, and how tight?
SELECT trade_date, open_price, high_price, low_price, close, volume,
       round(((high_price - low_price) / NULLIF(close,0) * 100)::numeric, 2) AS range_pct
  FROM mi_daily_closes WHERE ticker='MRNA' AND trade_date BETWEEN DATE '2026-09-10' AND DATE '2026-09-18' ORDER BY 1;
