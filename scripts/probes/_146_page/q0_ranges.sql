-- #146 detection page (2026-10-11): table ranges the replay window and the universe reconstruction depend on. SELECT-only.
SELECT 'daily_closes' AS k, MIN(trade_date)::text AS lo, MAX(trade_date)::text AS hi, COUNT(*)::text AS n, COUNT(DISTINCT ticker)::text AS tickers FROM mi_daily_closes
UNION ALL
SELECT 'stock_scores', MIN(score_date)::text, MAX(score_date)::text, COUNT(*)::text, COUNT(DISTINCT ticker)::text FROM mi_stock_scores
UNION ALL
SELECT 'stock_scores_days', MIN(score_date)::text, MAX(score_date)::text, COUNT(DISTINCT score_date)::text, '' FROM mi_stock_scores
UNION ALL
SELECT 'flag_cand', MIN(scan_date)::text, MAX(scan_date)::text, COUNT(*)::text, COUNT(DISTINCT scan_date)::text FROM mi_flag_candidates
UNION ALL
SELECT 'daily_closes_2025h2', MIN(trade_date)::text, MAX(trade_date)::text, COUNT(*)::text, COUNT(DISTINCT ticker)::text FROM mi_daily_closes WHERE trade_date >= '2025-07-01';
