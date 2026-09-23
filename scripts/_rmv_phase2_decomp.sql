-- #54 decomposition (READ-ONLY): the locked-spec catch set collapsed 530 (5/24) -> 0 (6/16 window).
-- Locate WHERE: window aging-out, a regime shift (fewer tight setups), or a column regression.

\echo '== scan freshness + window row counts =='
SELECT MAX(scan_date) AS last_scan,
       COUNT(*) FILTER (WHERE scan_date > CURRENT_DATE - 35) AS rows_35d,
       COUNT(*) FILTER (WHERE scan_date > CURRENT_DATE - 35 AND rmv_5d IS NOT NULL) AS rmv_pop_35d,
       COUNT(*) FILTER (WHERE scan_date > CURRENT_DATE - 35 AND rmv_5d <= 10) AS rmv_low_35d
FROM mi_flag_candidates;

\echo '== structural-filter funnel in the 35d window (where do rows drop out?) =='
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE rmv_5d IS NOT NULL) AS has_rmv,
  COUNT(*) FILTER (WHERE rmv_5d <= 10) AS rmv_low,
  COUNT(*) FILTER (WHERE rmv_5d <= 10 AND base_age >= 3) AS plus_baseage,
  COUNT(*) FILTER (WHERE rmv_5d <= 10 AND base_age >= 3 AND sma_10 IS NOT NULL AND sma_20 IS NOT NULL) AS plus_sma_notnull,
  COUNT(*) FILTER (WHERE rmv_5d <= 10 AND base_age >= 3 AND sma_10 IS NOT NULL AND sma_20 IS NOT NULL
                     AND breakout_close > sma_10 AND sma_10 > sma_20) AS plus_ma_aligned
FROM mi_flag_candidates WHERE scan_date > CURRENT_DATE - 35;

\echo '== same funnel over a WIDER 60d window (did the 530-era just age out?) =='
SELECT
  COUNT(*) FILTER (WHERE rmv_5d <= 10) AS rmv_low,
  COUNT(*) FILTER (WHERE rmv_5d <= 10 AND base_age >= 3 AND sma_10 IS NOT NULL AND sma_20 IS NOT NULL
                     AND breakout_close > sma_10 AND sma_10 > sma_20) AS structural_rmv_low,
  MIN(scan_date) AS oldest, MAX(scan_date) AS newest
FROM mi_flag_candidates WHERE scan_date > CURRENT_DATE - 60;

\echo '== column-population sanity in the 35d window (regression check) =='
SELECT
  COUNT(*) AS n,
  COUNT(base_age) AS base_age_pop,
  COUNT(sma_10) AS sma10_pop,
  COUNT(sma_20) AS sma20_pop,
  COUNT(rmv_5d) AS rmv5_pop,
  COUNT(breakout_close) AS bclose_pop
FROM mi_flag_candidates WHERE scan_date > CURRENT_DATE - 35;
