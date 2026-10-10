WITH days AS (SELECT DISTINCT scan_date FROM mi_flag_candidates ORDER BY scan_date DESC LIMIT 60)
SELECT CASE WHEN scan_date < '2026-09-08' THEN 'A_pre0908' WHEN scan_date < '2026-09-29' THEN 'B_0908_0928' ELSE 'C_0929on' END era,
  stage, substring(reason from '^[a-z_]+[a-z]') prefix, COUNT(*) n, COUNT(DISTINCT scan_date) days, COUNT(DISTINCT ticker) tickers
FROM mi_flag_candidates WHERE scan_date IN (SELECT scan_date FROM days) AND stage IN ('unqualified','INVALIDATED')
GROUP BY 1,2,3 ORDER BY 1,2,4 DESC;
