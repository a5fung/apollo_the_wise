-- #146 detection page (2026-10-11) — the replay POPULATION, a deliberate SUPERSET of what the shipped
-- detector can admit. SELECT-only, captured once.
--
-- The detector's pole gate is pivot_high / min(low over the 40 sessions ending at the pivot) >= 1.90
-- (flag_detector._RUNUP_MIN_RATIO / _RUNUP_LOOKBACK_DAYS). A rolling 40-row max(high)/min(low) at the
-- pivot day is >= that ratio, so "some day with hi40/lo40 >= 1.9" is a superset of every pole the code
-- can accept. The flag then forms within 25 sessions of the pivot (_PIVOT_LOOKBACK_DAYS), so a ticker
-- whose last qualifying day is >= 25 sessions before the replay window cannot produce a row inside it:
-- qualifying days are counted from 2024-11-01 for a window that starts 2025-01-02.
-- Volume: the detector needs a 20-session MEDIAN volume >= 500k on the SCAN day; the ticker-level
-- max of the 20-session MEAN over the whole span >= 350k is a loose superset (flag volume dries up,
-- and mean >= median on right-skewed volume). Price: the universe's close >= $5 gate loosened to $4.
-- Security type: CS / ADRC / unknown, the same filter get_flag_universe applies (an ETF is not a flag).
-- Everything else (ADR, depth, trend, Stage-2, pole volume) is left to the code.
WITH b AS (
  SELECT d.ticker, d.trade_date, d.close, d.volume,
         MAX(d.high_price) OVER w40 AS hi40,
         MIN(d.low_price)  OVER w40 AS lo40,
         COUNT(*)          OVER w40 AS n40,
         AVG(d.volume)     OVER w20 AS avgvol20
  FROM mi_daily_closes d
  WHERE d.trade_date >= '2024-08-01'
  WINDOW w40 AS (PARTITION BY d.ticker ORDER BY d.trade_date ROWS BETWEEN 39 PRECEDING AND CURRENT ROW),
         w20 AS (PARTITION BY d.ticker ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
),
s AS (
  SELECT ticker, trade_date, close, avgvol20, hi40, lo40,
         (n40 = 40 AND lo40 > 0 AND hi40 / lo40 >= 1.9 AND close >= 4) AS pole_ok
  FROM b
  WHERE trade_date >= '2024-11-01'
),
agg AS (
  SELECT ticker,
         COUNT(*) FILTER (WHERE pole_ok)           AS pole_days,
         MIN(trade_date) FILTER (WHERE pole_ok)    AS first_pole_day,
         MAX(trade_date) FILTER (WHERE pole_ok)    AS last_pole_day,
         ROUND(MAX(hi40 / NULLIF(lo40, 0))::numeric, 2) AS max_ratio,
         ROUND(MAX(avgvol20)::numeric)             AS max_avgvol20,
         COUNT(*)                                  AS days_in_span
  FROM s
  GROUP BY ticker
)
SELECT a.ticker, a.pole_days, a.first_pole_day, a.last_pole_day, a.max_ratio, a.max_avgvol20, a.days_in_span,
       COALESCE(st.security_type, '?') AS sec_type
FROM agg a
LEFT JOIN mi_security_types st ON st.ticker = a.ticker
WHERE a.pole_days > 0
  AND a.max_avgvol20 >= 350000
  AND (st.security_type IN ('CS', 'ADRC') OR st.ticker IS NULL)
ORDER BY a.ticker;
