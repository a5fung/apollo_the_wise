SET default_transaction_read_only = on;
-- INDEPENDENT recount (different formulation: per-ticker window functions over the ticker's own rows)
WITH u AS (SELECT d.ticker, d.close, d.high_price h, d.low_price l FROM mi_daily_closes d JOIN mi_security_types t USING (ticker)
           WHERE d.trade_date = DATE '2026-11-04' AND t.security_type IN ('CS','ADRC') AND d.close >= 1),
prev AS (SELECT DISTINCT ON (d.ticker) d.ticker, d.close pc FROM mi_daily_closes d JOIN u USING (ticker)
         WHERE d.trade_date < DATE '2026-11-04' AND d.trade_date >= DATE '2026-10-20' AND d.close > 0 ORDER BY d.ticker, d.trade_date DESC),
yr AS (SELECT d.ticker, max(d.high_price) FILTER (WHERE d.high_price>0) mh, min(d.low_price) FILTER (WHERE d.low_price>0) ml, count(*) n
       FROM mi_daily_closes d JOIN u USING (ticker)
       WHERE d.trade_date < DATE '2026-11-04' AND d.trade_date >= (SELECT min(trade_date) FROM (SELECT DISTINCT trade_date FROM mi_daily_closes WHERE trade_date < DATE '2026-11-04' AND trade_date > DATE '2025-09-01' ORDER BY trade_date DESC LIMIT 252) z)
       AND d.close > 0 GROUP BY d.ticker)
SELECT count(*) AS universe,
  count(*) FILTER (WHERE p.pc IS NOT NULL AND u.close > p.pc) AS adv,
  count(*) FILTER (WHERE p.pc IS NOT NULL AND u.close < p.pc) AS dec,
  count(*) FILTER (WHERE p.pc IS NOT NULL AND u.close = p.pc) AS unch,
  count(*) FILTER (WHERE y.n >= 245 AND u.h > 0 AND u.h >= y.mh) AS nh,
  count(*) FILTER (WHERE y.n >= 245 AND u.l > 0 AND u.l <= y.ml) AS nl,
  count(*) FILTER (WHERE y.n >= 245 AND u.h > 0 AND u.l > 0) AS eligible
FROM u LEFT JOIN prev p USING (ticker) LEFT JOIN yr y USING (ticker);
