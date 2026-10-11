-- #146 unpark: DRY RUN of the htf.md "Bucket the TRIGGERED reads" SELECTs on prod BEFORE the column exists.
-- The column is simulated by the CTE with exactly what the exactly-once backfill will write ('coiled' on every raw
-- TRIGGERED row), so this shows the SELECTs parse and join, and what they return on day one.
-- Statement A = raw reads per bucket (mi_flag_candidates alone). Statement B = the intraday breakout shadow per bucket.
-- SELECT-only, captured once.
WITH c AS (
    SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from
    FROM mi_flag_candidates
)
SELECT 'A' AS q, triggered_from AS bucket, NULL::text AS parent_stage, count(*) AS n,
       min(scan_date)::text AS first_seen, max(scan_date)::text AS last_seen,
       NULL::bigint AS settled, NULL::bigint AS capture, NULL::float AS med_realized_r
FROM c
WHERE stage = 'TRIGGERED' AND held_from_stage IS NULL
GROUP BY triggered_from
UNION ALL
SELECT 'B', COALESCE(c.triggered_from, 'no EOD TRIGGERED read'), s.parent_stage, count(*),
       min(s.break_date)::text, max(s.break_date)::text,
       count(*) FILTER (WHERE s.outcome IS NOT NULL),
       count(*) FILTER (WHERE s.outcome = 'capture'),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY s.realized_r) FILTER (WHERE s.outcome IS NOT NULL)
FROM mi_htf_breakout_shadow s
LEFT JOIN c ON c.ticker = s.ticker AND c.scan_date = s.break_date
           AND c.stage = 'TRIGGERED' AND c.held_from_stage IS NULL
GROUP BY COALESCE(c.triggered_from, 'no EOD TRIGGERED read'), s.parent_stage
ORDER BY 1, 2, 3;
