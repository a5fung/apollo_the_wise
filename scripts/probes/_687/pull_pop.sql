-- #687 read-only prod pull 2 (captured once): the REBUILT EP-like candidate rows, 2024-01-02 .. 2026-04-30.
-- Rules fixed BEFORE any outcome (STEP 0): gap >= 9% (day open vs prior close); prior close >= $5; prior-day volume
-- >= 50,000; 20-session median $volume over [D-30 calendar days, D-1] >= $1M with >= 10 rows (the live
-- _check_adv_dollar_volume window as it stands at 09:31, when the day's own row does not exist yet); extension =
-- (prev_close - min close over [D-10 calendar days, D-1]) / min < 50% (the live extension_map window);
-- ticker <= 5 upper-case letters (MAX_TICKER_LEN, warrants/units out). The VOLUME PROXY for the live RVOL rule
-- (gap-day volume >= 3x the mean volume of the prior 20 sessions) is carried as a COLUMN (vol_mult) so the
-- composition can show what it removes; it is applied in Python. Cooldown (60d) is applied in Python.
\echo === POP ===
WITH b AS (
  SELECT ticker, trade_date, open_price AS o, high_price AS h, low_price AS l, close AS c, volume AS v,
         lag(close) OVER w AS pc, lag(volume) OVER w AS pv, lag(trade_date) OVER w AS pdate,
         avg(volume) OVER (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avgv20,
         count(*) OVER (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS n20
  FROM mi_daily_closes
  WHERE trade_date >= '2023-10-01' AND trade_date <= '2026-04-30'
    AND length(ticker) <= 5 AND ticker ~ '^[A-Z]+$'
  WINDOW w AS (PARTITION BY ticker ORDER BY trade_date)
),
g AS (
  SELECT * FROM b
  WHERE trade_date >= '2024-01-02' AND pc >= 5 AND pv >= 50000 AND o IS NOT NULL AND pc > 0
    AND (o - pc) / pc * 100 >= 9
),
e AS (
  SELECT g.*, x.low_close, m.adv_dollar, m.nadv
  FROM g
  LEFT JOIN LATERAL (
    SELECT min(close) AS low_close FROM mi_daily_closes d
    WHERE d.ticker = g.ticker AND d.trade_date >= g.trade_date - 10 AND d.trade_date < g.trade_date) x ON true
  LEFT JOIN LATERAL (
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY close * volume) AS adv_dollar, count(*) AS nadv
    FROM mi_daily_closes d
    WHERE d.ticker = g.ticker AND d.trade_date >= g.trade_date - 30 AND d.trade_date < g.trade_date AND d.volume > 0) m ON true
)
SELECT ticker, trade_date, o, h, l, c, v, pc, pv, pdate, round(avgv20::numeric, 0) AS avgv20, n20,
       round(((o - pc) / pc * 100)::numeric, 2) AS gap_pct,
       low_close, round(((pc - low_close) / low_close * 100)::numeric, 2) AS ext_pct,
       round(adv_dollar::numeric, 0) AS adv_dollar, nadv,
       round((v / NULLIF(avgv20, 0))::numeric, 2) AS vol_mult
FROM e
WHERE low_close IS NOT NULL AND (pc - low_close) / low_close * 100 < 50
  AND nadv >= 10 AND adv_dollar >= 1000000
ORDER BY trade_date, ticker;
