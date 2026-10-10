WITH days AS (SELECT DISTINCT scan_date FROM mi_flag_candidates ORDER BY scan_date DESC LIMIT 60),
dl AS (SELECT scan_date, LEAD(scan_date) OVER (ORDER BY scan_date) nxt FROM days),
w AS (SELECT ticker, scan_date, stage, LEAD(scan_date) OVER (PARTITION BY ticker ORDER BY scan_date) nd,
             LEAD(stage) OVER (PARTITION BY ticker ORDER BY scan_date) ns, LEAD(reason) OVER (PARTITION BY ticker ORDER BY scan_date) nr
      FROM mi_flag_candidates WHERE scan_date >= (SELECT MIN(scan_date) FROM days))
SELECT 'watch_next' q, CASE WHEN w.nd IS NULL OR w.nd > dl.nxt THEN 'NO ROW next scan day (universe drop)' WHEN ns='unqualified' THEN 'unq:'||split_part(nr,'_',1) ELSE ns END k, COUNT(*)::text n, COUNT(DISTINCT ticker)::text t
FROM w JOIN dl ON dl.scan_date=w.scan_date WHERE w.stage='WATCH' AND dl.nxt IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'wday_adr', trade_date::text, round(((high_price-low_price)/close*100)::numeric,2)::text, volume::text FROM mi_daily_closes WHERE ticker='WDAY' AND trade_date BETWEEN '2026-08-01' AND '2026-09-17'
ORDER BY 1,2;
