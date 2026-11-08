SET default_transaction_read_only = on;
-- INDEPENDENT recount for 2026-11-06, written separately from the export: prev = the ticker's close on the
-- previous session 2026-11-05 exactly (the export's rule); highs/lows vs the prior 252 sessions, >= 245 bars.
WITH sess AS (SELECT trade_date FROM mi_daily_closes d JOIN mi_security_types t USING (ticker)
              WHERE t.security_type IN ('CS','ADRC') AND d.trade_date < DATE '2026-11-06' AND d.trade_date > DATE '2025-06-01'
              GROUP BY trade_date HAVING count(*) >= 3000 ORDER BY trade_date DESC LIMIT 252),
u AS (SELECT d.ticker, d.close, d.high_price h, d.low_price l FROM mi_daily_closes d JOIN mi_security_types t USING (ticker)
      WHERE d.trade_date = DATE '2026-11-06' AND t.security_type IN ('CS','ADRC') AND d.close >= 1 AND d.close <> 'NaN'),
prev AS (SELECT d.ticker, d.close pc FROM mi_daily_closes d JOIN u USING (ticker)
         WHERE d.trade_date = DATE '2026-11-05' AND d.close > 0 AND d.close <> 'NaN'),
yr AS (SELECT d.ticker, max(d.high_price) mh, min(d.low_price) ml, count(*) n
       FROM mi_daily_closes d JOIN u USING (ticker) JOIN sess s ON s.trade_date = d.trade_date
       WHERE d.high_price > 0 AND d.low_price > 0 AND d.high_price <> 'NaN' AND d.low_price <> 'NaN' AND d.close > 0
       GROUP BY d.ticker)
SELECT count(*) AS universe,
  count(*) FILTER (WHERE p.pc IS NOT NULL AND u.close > p.pc) AS adv,
  count(*) FILTER (WHERE p.pc IS NOT NULL AND u.close < p.pc) AS dec,
  count(*) FILTER (WHERE p.pc IS NOT NULL AND u.close = p.pc) AS unch,
  count(*) FILTER (WHERE p.pc IS NULL) AS no_prior,
  count(*) FILTER (WHERE y.n >= 245 AND u.h > 0 AND u.l > 0 AND u.h >= y.mh) AS nh,
  count(*) FILTER (WHERE y.n >= 245 AND u.h > 0 AND u.l > 0 AND u.l <= y.ml) AS nl,
  count(*) FILTER (WHERE y.n >= 245 AND u.h > 0 AND u.l > 0) AS eligible
FROM u LEFT JOIN prev p USING (ticker) LEFT JOIN yr y USING (ticker);
