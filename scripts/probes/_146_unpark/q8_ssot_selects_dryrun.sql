\echo '== Q0: exactly the SQL in htf.md, column simulated =='
SELECT triggered_from AS bucket, count(*) AS reads, min(scan_date) AS first_seen, max(scan_date) AS last_seen
FROM (SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from FROM mi_flag_candidates) mi_flag_candidates
WHERE stage = 'TRIGGERED' AND held_from_stage IS NULL AND scan_date >= DATE '2026-06-27'
GROUP BY triggered_from ORDER BY 1;
\echo '== Q1: exactly the SQL in htf.md, column simulated =='
SELECT COALESCE(c.triggered_from, 'no EOD TRIGGERED read') AS bucket, s.parent_stage,
       count(*) AS breaks,
       count(*) FILTER (WHERE s.outcome IS NOT NULL) AS settled,
       count(*) FILTER (WHERE s.outcome = 'capture') AS capture,
       count(*) FILTER (WHERE s.outcome = 'stop') AS stop,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY s.realized_r) FILTER (WHERE s.outcome IS NOT NULL) AS med_realized_r
FROM mi_htf_breakout_shadow s
LEFT JOIN (SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from FROM mi_flag_candidates) c ON c.ticker = s.ticker AND c.scan_date = s.break_date
                              AND c.stage = 'TRIGGERED' AND c.held_from_stage IS NULL
GROUP BY 1, 2 ORDER BY 1, 2;
\echo '== Q2: exactly the SQL in htf.md, column simulated =='
SELECT c.triggered_from AS bucket, count(*) AS reads,
       count(*) FILTER (WHERE f.n = 10) AS settled_10_sessions,
       count(*) FILTER (WHERE f.n = 10 AND f.min_close < c.base_low) AS closed_under_base_low_within_10
FROM (SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from FROM mi_flag_candidates) c
CROSS JOIN LATERAL (SELECT count(*) AS n, min(x.close) AS min_close
                    FROM (SELECT d.close FROM mi_daily_closes d
                          WHERE d.ticker = c.ticker AND d.trade_date > c.scan_date
                          ORDER BY d.trade_date LIMIT 10) x) f
WHERE c.stage = 'TRIGGERED' AND c.held_from_stage IS NULL AND c.scan_date >= DATE '2026-06-27'
GROUP BY c.triggered_from ORDER BY 1;
