SET default_transaction_read_only = on;
-- breakout v1's RS gate for ODD at D = 2026-09-08: best of the 21/63/126-session return percentiles across the v1 universe
-- (raw close >= $2, 20-session median dollar volume >= $5M, common stock / ADR), measured that night
WITH px AS (
  SELECT c.ticker, c.trade_date, c.close,
         ROW_NUMBER() OVER (PARTITION BY c.ticker ORDER BY c.trade_date DESC) AS k,
         c.close * c.volume AS dv
  FROM mi_daily_closes c JOIN mi_security_types s ON s.ticker = c.ticker AND s.security_type IN ('CS','ADRC')
  WHERE c.trade_date <= DATE '2026-10-08' AND c.trade_date >= DATE '2026-10-08' - 220
), agg AS (
  SELECT ticker,
         max(close) FILTER (WHERE k = 1) AS c0, max(close) FILTER (WHERE k = 22) AS c21,
         max(close) FILTER (WHERE k = 64) AS c63, max(close) FILTER (WHERE k = 127) AS c126,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY dv) FILTER (WHERE k <= 20) AS dv20,
         max(trade_date) FILTER (WHERE k = 1) AS last_d
  FROM px GROUP BY ticker
), u AS (
  SELECT ticker, c0/c21-1 AS r21, c0/c63-1 AS r63, c0/c126-1 AS r126 FROM agg
  WHERE last_d = DATE '2026-10-08' AND c0 >= 2 AND dv20 >= 5e6 AND c21 > 0 AND c63 > 0 AND c126 > 0
), p AS (
  SELECT ticker, r21, r63, r126,
         100*percent_rank() OVER (ORDER BY r21) AS p21, 100*percent_rank() OVER (ORDER BY r63) AS p63, 100*percent_rank() OVER (ORDER BY r126) AS p126,
         count(*) OVER () AS n
  FROM u
)
SELECT ticker, n, round(r21::numeric,3) r21, round(r63::numeric,3) r63, round(r126::numeric,3) r126,
       round(p21::numeric,1) p21, round(p63::numeric,1) p63, round(p126::numeric,1) p126, round(greatest(p21,p63,p126)::numeric,1) AS rs_best
FROM p WHERE ticker IN ('ODD');
\echo == bars
SELECT trade_date, open_price, high_price, low_price, close, volume FROM mi_daily_closes WHERE ticker='ODD' AND trade_date >= '2026-03-01' AND trade_date <= '2026-10-16' ORDER BY trade_date;
