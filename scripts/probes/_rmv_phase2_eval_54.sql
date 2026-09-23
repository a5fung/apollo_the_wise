-- #54 rmv_phase2_evaluation — the OVERDUE forward-return eval (READ-ONLY).
-- LOCKED spec (advisor 2026-05-09, data_gated_reviews.yaml:1266-1300): does RMV-low (<=10) among
-- STRUCTURALLY-VALID flag candidates that Apollo rates WATCH/TIGHTENING (not COILED) show a >=5pp
-- forward-return lift over the structurally-valid baseline? >=5pp -> Phase 3 (rmv_5d<=10 as alt
-- COILED qualifier); <5pp -> RMV redundant with _compute_fresh_tightening; catch_n<30 -> defer.

\echo '== Part 1: divergence counts (RMV-low among structurally-valid) =='
WITH rmv_low AS (
  SELECT scan_date, ticker, stage, rmv_5d
  FROM mi_flag_candidates
  WHERE rmv_5d <= 10
    AND base_age >= 3
    AND sma_10 IS NOT NULL AND sma_20 IS NOT NULL
    AND breakout_close > sma_10 AND sma_10 > sma_20
    AND scan_date > CURRENT_DATE - 35
)
SELECT COUNT(*) AS rmv_low_n,
       COUNT(*) FILTER (WHERE stage = 'COILED') AS overlap_coiled,
       COUNT(*) FILTER (WHERE stage IN ('WATCH','TIGHTENING')) AS rmv_catches_apollo_misses
FROM rmv_low;

\echo '== Part 2: forward-return lift (catch subset vs structurally-valid baseline; fwd_5d_max_high) =='
WITH cand AS (
  SELECT c.scan_date, c.ticker, c.stage, c.rmv_5d, c.base_age, c.breakout_close,
         f.fwd_high
  FROM mi_flag_candidates c
  LEFT JOIN LATERAL (
    SELECT MAX(high_price) AS fwd_high
    FROM (SELECT high_price FROM mi_daily_closes d
          WHERE d.ticker = c.ticker AND d.trade_date > c.scan_date
          ORDER BY d.trade_date LIMIT 5) x
  ) f ON TRUE
  WHERE c.scan_date > CURRENT_DATE - 35
    AND c.base_age >= 3
    AND c.sma_10 IS NOT NULL AND c.sma_20 IS NOT NULL
    AND c.breakout_close > c.sma_10 AND c.sma_10 > c.sma_20
    AND c.breakout_close > 0
),
scored AS (
  SELECT *, (fwd_high / breakout_close - 1.0) AS fwd5
  FROM cand WHERE fwd_high IS NOT NULL
),
catch AS (SELECT * FROM scored WHERE rmv_5d <= 10 AND stage IN ('WATCH','TIGHTENING'))
SELECT
  (SELECT COUNT(*) FROM scored) AS baseline_n,
  round((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd5) FROM scored)::numeric*100, 2) AS baseline_med_fwd5_pct,
  (SELECT COUNT(*) FROM catch) AS catch_n,
  round((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd5) FROM catch)::numeric*100, 2) AS catch_med_fwd5_pct,
  round(((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd5) FROM catch)
        - (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd5) FROM scored))::numeric*100, 2) AS lift_pp;
