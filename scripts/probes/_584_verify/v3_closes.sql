COPY (SELECT c.ticker, c.trade_date, c.open_price, c.high_price, c.low_price, c.close, c.volume
FROM mi_daily_closes c
WHERE c.trade_date BETWEEN '2026-07-20' AND '2026-09-30'
  AND c.ticker IN (SELECT DISTINCT ticker FROM mi_universe_floor_shadow WHERE scan_date <= '2026-09-30')
ORDER BY c.ticker, c.trade_date) TO STDOUT WITH CSV HEADER;
