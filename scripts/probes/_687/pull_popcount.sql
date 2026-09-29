-- #687 read-only prod pull 2: COUNT the rebuilt EP-like population before pulling anything else.
-- Rules (fixed before any outcome): gap >= 9% (open vs prior close), prior close >= $5, prior-day volume >= 50k,
-- 20-session median $vol (through D-1) >= $1M, extension (prev_close vs min close of prior 5 sessions) < 50%,
-- volume proxy: gap-day volume >= 3x the mean volume of the prior 20 sessions; ticker <= 5 alpha chars.
\echo === POPCOUNT ===
WITH b AS (
  SELECT ticker, trade_date, open_price AS o, high_price AS h, low_price AS l, close AS c, volume AS v,
         lag(close) OVER w AS pc, lag(volume) OVER w AS pv,
         min(close) OVER (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS low5,
         avg(volume) OVER (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avgv20,
         count(*) OVER (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS n20,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY close * volume) OVER () AS dummy
  FROM mi_daily_closes
  WHERE trade_date >= '2023-11-01' AND trade_date <= '2026-04-30'
    AND length(ticker) <= 5 AND ticker ~ '^[A-Z]+$'
  WINDOW w AS (PARTITION BY ticker ORDER BY trade_date)
)
SELECT 1;
