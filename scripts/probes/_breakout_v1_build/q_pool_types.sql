SET default_transaction_read_only = on;
-- the $2 / $5M universe on the latest stored session, by security type (who would sit in the strength ranking)
WITH last AS (SELECT max(trade_date) d FROM mi_daily_closes),
px AS (
  SELECT c.ticker, c.trade_date, c.close, c.close*c.volume dv, ROW_NUMBER() OVER (PARTITION BY c.ticker ORDER BY c.trade_date DESC) k
  FROM mi_daily_closes c, last WHERE c.trade_date > last.d - 40 AND c.trade_date <= last.d
), u AS (
  SELECT ticker FROM px GROUP BY ticker
  HAVING max(close) FILTER (WHERE k=1) >= 2 AND percentile_cont(0.5) WITHIN GROUP (ORDER BY dv) FILTER (WHERE k<=20) >= 5e6
     AND max(trade_date) = (SELECT d FROM last)
)
SELECT coalesce(s.security_type,'(untyped)') AS type, count(*) FROM u LEFT JOIN mi_security_types s USING (ticker) GROUP BY 1 ORDER BY 2 DESC;
