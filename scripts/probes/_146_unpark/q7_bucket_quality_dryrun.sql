-- #146 unpark: DRY RUN (column simulated, as in q5) of the htf.md "Q2 - did each bucket's breakouts hold" SELECT: the
-- detection-quality column the 146 detection page used - a close under the base LOW within the next 10 sessions.
-- On day one every historical raw read is 'coiled', so this reproduces the shipped-rule baseline on STORED reads.
-- SELECT-only, captured once.
WITH c AS (
    SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from
    FROM mi_flag_candidates
)
SELECT c.triggered_from AS bucket,
       count(*) AS reads,
       count(*) FILTER (WHERE f.n = 10) AS settled_10_sessions,
       count(*) FILTER (WHERE f.n = 10 AND f.min_close < c.base_low) AS closed_under_base_low_within_10,
       round((100.0 * count(*) FILTER (WHERE f.n = 10 AND f.min_close < c.base_low)
              / NULLIF(count(*) FILTER (WHERE f.n = 10), 0))::numeric, 1) AS pct_under_base_low
FROM c
CROSS JOIN LATERAL (
    SELECT count(*) AS n, min(x.close) AS min_close
    FROM (SELECT d.close FROM mi_daily_closes d
          WHERE d.ticker = c.ticker AND d.trade_date > c.scan_date
          ORDER BY d.trade_date LIMIT 10) x
) f
WHERE c.stage = 'TRIGGERED' AND c.held_from_stage IS NULL
GROUP BY c.triggered_from
ORDER BY 1;
