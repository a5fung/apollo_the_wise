\echo '== Q9: the day-one raw TRIGGERED reads by rule era (column simulated; SELECT-only) =='
-- 2026-06-27 = the sourced HTF rebuild (htf.md change log). Before it the retired 50%/60-session pole rule read the board.
SELECT CASE WHEN c.scan_date >= DATE '2026-06-27' THEN 'post-rebuild' ELSE 'pre-rebuild (retired rule)' END AS era,
       count(*) AS reads, min(c.scan_date) AS first_seen, max(c.scan_date) AS last_seen,
       count(*) FILTER (WHERE f.n = 10) AS settled_10_sessions,
       count(*) FILTER (WHERE f.n = 10 AND f.min_close < c.base_low) AS closed_under_base_low_within_10
FROM (SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from FROM mi_flag_candidates) c
CROSS JOIN LATERAL (SELECT count(*) AS n, min(x.close) AS min_close
                    FROM (SELECT d.close FROM mi_daily_closes d
                          WHERE d.ticker = c.ticker AND d.trade_date > c.scan_date
                          ORDER BY d.trade_date LIMIT 10) x) f
WHERE c.stage = 'TRIGGERED' AND c.held_from_stage IS NULL
GROUP BY 1 ORDER BY 1 DESC;
