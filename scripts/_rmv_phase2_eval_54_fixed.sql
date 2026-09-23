-- #54 rmv_phase2_evaluation — CORRECTED (READ-ONLY). The locked spec's MA-alignment guard used
-- `breakout_close` (set ONLY on TRIGGERED rows, flag_detector.py:637) while filtering for
-- WATCH/TIGHTENING stages => structurally-empty catch set (a latent bug; the 5/24 "530" was never
-- reproducible via that SQL). FIX: use the candidate's CURRENT close at scan_date (mi_daily_closes,
-- == the flag scan's `close_today`) as the MA-alignment reference. Logic otherwise = the locked spec.

\echo '== Part 1: divergence counts (fixed MA-alignment via current close) =='
WITH rmv_low AS (
  SELECT c.scan_date, c.ticker, c.stage, c.rmv_5d
  FROM mi_flag_candidates c
  JOIN mi_daily_closes dc ON dc.ticker = c.ticker AND dc.trade_date = c.scan_date
  WHERE c.rmv_5d <= 10
    AND c.base_age >= 3
    AND c.sma_10 IS NOT NULL AND c.sma_20 IS NOT NULL
    AND dc.close > c.sma_10 AND c.sma_10 > c.sma_20
    AND c.scan_date > CURRENT_DATE - 35
)
SELECT COUNT(*) AS rmv_low_n,
       COUNT(*) FILTER (WHERE stage = 'COILED') AS overlap_coiled,
       COUNT(*) FILTER (WHERE stage IN ('WATCH','TIGHTENING')) AS rmv_catches_apollo_misses
FROM rmv_low;

\echo '== Part 2: forward-return lift (catch vs structurally-valid baseline; fwd_5d_max_high) =='
WITH cand AS (
  SELECT c.scan_date, c.ticker, c.stage, c.rmv_5d, dc.close AS cur_close, f.fwd_high
  FROM mi_flag_candidates c
  JOIN mi_daily_closes dc ON dc.ticker = c.ticker AND dc.trade_date = c.scan_date
  LEFT JOIN LATERAL (
    SELECT MAX(high_price) AS fwd_high
    FROM (SELECT high_price FROM mi_daily_closes d
          WHERE d.ticker = c.ticker AND d.trade_date > c.scan_date
          ORDER BY d.trade_date LIMIT 5) x
  ) f ON TRUE
  WHERE c.scan_date > CURRENT_DATE - 35
    AND c.base_age >= 3
    AND c.sma_10 IS NOT NULL AND c.sma_20 IS NOT NULL
    AND dc.close > c.sma_10 AND c.sma_10 > c.sma_20
    AND dc.close > 0
),
scored AS (SELECT *, (fwd_high / cur_close - 1.0) AS fwd5 FROM cand WHERE fwd_high IS NOT NULL),
catch AS (SELECT * FROM scored WHERE rmv_5d <= 10 AND stage IN ('WATCH','TIGHTENING'))
SELECT
  (SELECT COUNT(*) FROM scored) AS baseline_n,
  round((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd5) FROM scored)::numeric*100, 2) AS baseline_med_fwd5_pct,
  (SELECT COUNT(*) FROM catch) AS catch_n,
  round((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd5) FROM catch)::numeric*100, 2) AS catch_med_fwd5_pct,
  round(((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd5) FROM catch)
        - (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd5) FROM scored))::numeric*100, 2) AS lift_pp;
