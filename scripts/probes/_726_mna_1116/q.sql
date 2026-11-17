SET default_transaction_read_only = on;
\echo BRZE_BARS
SELECT trade_date, close, high_price, low_price, volume,
 round((100*(high_price-low_price)/close)::numeric,2) rng
FROM mi_daily_closes WHERE ticker='BRZE' ORDER BY trade_date DESC LIMIT 12;
\echo PINNED_ALL
WITH recent AS (
  SELECT ticker, trade_date, close, high_price, low_price, volume,
   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) rn
  FROM mi_daily_closes WHERE trade_date > DATE '2026-11-16' - 180 AND trade_date <= DATE '2026-11-16'),
pin AS (SELECT ticker FROM recent WHERE rn<=4 GROUP BY ticker HAVING count(*)=4
  AND bool_and((high_price-low_price)/NULLIF(close,0) < 0.02)),
chg AS (SELECT ticker, trade_date, 100.0*(close/NULLIF(LAG(close) OVER w,0)-1) pct,
  volume::numeric/NULLIF(AVG(volume) OVER (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING),0) rvol
  FROM recent WINDOW w AS (PARTITION BY ticker ORDER BY trade_date)),
ann AS (SELECT ticker, max(trade_date) d, max(pct) pct, max(rvol) rvol FROM chg WHERE pct>=15 AND rvol>=10 GROUP BY ticker)
SELECT p.ticker, a.d, round(a.pct::numeric,1), round(a.rvol::numeric,1) FROM pin p JOIN ann a USING (ticker) ORDER BY 1;
\echo BRZE_BIG_DAYS
SELECT trade_date, round(pct::numeric,1), round(rvol::numeric,1) FROM (
 SELECT trade_date, 100.0*(close/NULLIF(LAG(close) OVER w,0)-1) pct,
  volume::numeric/NULLIF(AVG(volume) OVER (ORDER BY trade_date ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING),0) rvol
 FROM mi_daily_closes WHERE ticker='BRZE' AND trade_date > DATE '2026-11-16'-180 WINDOW w AS (ORDER BY trade_date)) x
WHERE pct >= 8 ORDER BY 1;
