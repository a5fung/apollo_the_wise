SET default_transaction_read_only = on;
-- Era split of graded live alerts. Columns as named in the review entry; verify against schema on first run.
-- Era A: alert_date < 2026-08-27 (older rubric, 30 days to 09-01 -> expect 93)
-- Era B: 2026-08-27 .. 2026-09-01 (rubric v4, pre-wiring -> expect 6, the like-for-like comparator)
-- Era C: >= 2026-09-02 (rubric v4, wired -> predicate counts 40)
SELECT CASE WHEN alert_date < '2026-08-27' THEN 'A_older_rubric'
            WHEN alert_date <= '2026-09-01' THEN 'B_v4_prewiring'
            ELSE 'C_v4_wired' END AS era,
       judge_grade, judge_tier, COUNT(*)
FROM mi_ep_alerts
WHERE COALESCE(source,'live')='live' AND judge_grade IS NOT NULL
  AND alert_date >= '2026-08-02'
GROUP BY 1,2,3 ORDER BY 1,2,3;

-- Era B rows by name
SELECT alert_date, ticker, judge_grade, judge_tier
FROM mi_ep_alerts
WHERE COALESCE(source,'live')='live' AND judge_grade IS NOT NULL
  AND alert_date BETWEEN '2026-08-27' AND '2026-09-01'
ORDER BY alert_date, ticker;

-- Mechanism: how often the reason text cites the flags (era C vs era B)
SELECT CASE WHEN alert_date <= '2026-09-01' THEN 'B_prewiring' ELSE 'C_wired' END AS era,
       COUNT(*) n,
       SUM((judge_grade_reason ~* 'primary source|direct source|has_direct_source|company filing|press release')::int) cites_source,
       SUM((judge_grade_reason ~* 'revenue_stage|pre-revenue|revenue stage|revenue rule')::int) cites_revenue
FROM mi_ep_alerts
WHERE COALESCE(source,'live')='live' AND judge_grade IS NOT NULL AND alert_date >= '2026-08-27'
GROUP BY 1;
