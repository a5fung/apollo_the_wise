SET default_transaction_read_only = on;
WITH sess AS (SELECT trade_date, row_number() OVER (ORDER BY trade_date DESC)-1 AS idx FROM (SELECT c.trade_date FROM mi_daily_closes c JOIN mi_security_types t USING (ticker) WHERE c.trade_date >= DATE '2025-06-01' AND t.security_type IN ('CS','ADRC') GROUP BY 1 HAVING count(*)>=3000) x),
u AS (SELECT d.ticker FROM mi_daily_closes d JOIN mi_security_types t USING (ticker) WHERE d.trade_date = DATE '2026-11-04' AND t.security_type IN ('CS','ADRC') AND d.close >= 1),
n AS (SELECT u.ticker, count(d.*) FILTER (WHERE s.idx <= 209 AND d.close > 0) AS n210, min(s.idx) FILTER (WHERE d.close>0) AS newest, max(s.idx) FILTER (WHERE d.close > 0 AND s.idx <= 400) AS oldest
      FROM u LEFT JOIN mi_daily_closes d ON d.ticker = u.ticker AND d.trade_date >= DATE '2025-06-01' LEFT JOIN sess s ON s.trade_date = d.trade_date GROUP BY u.ticker)
SELECT CASE WHEN n210 = 210 THEN 'a full' WHEN oldest < 209 THEN 'b young (<210 sessions listed)' WHEN n210 >= 203 THEN 'c 1-7 missing' ELSE 'd 8+ missing' END AS k, count(*) FROM n GROUP BY 1 ORDER BY 1;
