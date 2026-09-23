-- #271 CLASS B breadth metric (READ-ONLY, gate-free) — daily count of common stocks up/down
-- >=20% over 5 trading days. Mirrors regime.py's common-stock filter (CS/ADRC or unknown,
-- close>=1.0) + a corporate-action guard (drop |5d move|>200%/<-90% = splits). Also emits a
-- $5 price-floor variant (Pradeep "real names" thrust) and the universe size (count-vs-% check).
WITH common AS (
  SELECT d.ticker, d.trade_date, d.close
  FROM mi_daily_closes d
  LEFT JOIN mi_security_types st ON st.ticker = d.ticker
  WHERE d.close IS NOT NULL AND d.close >= 1.0
    AND (st.security_type IN ('CS','ADRC') OR st.ticker IS NULL)
),
ret AS (
  SELECT ticker, trade_date, close,
    close / NULLIF(LAG(close,5) OVER (PARTITION BY ticker ORDER BY trade_date),0) - 1 AS r5
  FROM common
)
SELECT trade_date,
  COUNT(*) FILTER (WHERE r5 IS NOT NULL)                                  AS universe,
  COUNT(*) FILTER (WHERE r5 >=  0.20 AND r5 <=  2.0)                      AS up20,
  COUNT(*) FILTER (WHERE r5 <= -0.20 AND r5 >= -0.9)                      AS down20,
  COUNT(*) FILTER (WHERE r5 >=  0.20 AND r5 <=  2.0 AND close >= 5)       AS up20_p5,
  COUNT(*) FILTER (WHERE r5 <= -0.20 AND r5 >= -0.9 AND close >= 5)       AS down20_p5
FROM ret
GROUP BY trade_date
ORDER BY trade_date;
