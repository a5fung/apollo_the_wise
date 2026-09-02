-- #545 Phase 2 capture — the missed-EP tail read. READ-ONLY, run once, quote from the file.
-- setup_at_open = TRUE restricts to names that ACTUALLY gapped at the open (#595, 08-29),
-- which is what makes these buckets readable at all. ret_20d is the harvestable proxy;
-- max_high_* is MFE (positive by construction) and must NEVER be used as a return.
--
-- 🛑 UNIT: ret_1d/5d/20d ARE FRACTIONS, NOT PERCENTS. missed_outcomes.py:652 computes
--    (close_d20 - open_d0) / open_d0, so +29% is 0.29 and the ≥20%-at-20-days tail bar is 0.20.
--    The first run of this capture used `>= 20` and returned ZERO tail names in EVERY bucket with
--    a mean of 0.0 — a result that would have read as "no skipped EP has ever run", which is
--    false on its face (HTFL closed +29%). It was asking for +2000%. State the unit or repeat it.
\echo ===Q1_BUCKET_TAIL_SHARE===
SELECT skip_category,
       COUNT(*)                                              AS n,
       COUNT(*) FILTER (WHERE ret_20d >= 0.20)                 AS tail_ge20pct,
       ROUND((100.0 * COUNT(*) FILTER (WHERE ret_20d >= 0.20) / NULLIF(COUNT(*),0))::numeric,1) AS tail_pct,
       COUNT(*) FILTER (WHERE ret_20d < 0)                   AS losers,
       ROUND((100*AVG(ret_20d))::numeric,1)                        AS mean_ret20_pct,
       ROUND((100*percentile_cont(0.5) WITHIN GROUP (ORDER BY ret_20d))::numeric,1) AS median_ret20_pct,
       ROUND((100*MAX(ret_20d))::numeric,1)                        AS best_ret20_pct
FROM mi_ep_missed_outcomes
WHERE setup_at_open IS TRUE AND ret_20d IS NOT NULL
GROUP BY skip_category ORDER BY n DESC;

\echo ===Q2_SKIP_REASON_WITHIN_BUCKET===
SELECT skip_category, skip_reason, COUNT(*) AS n,
       COUNT(*) FILTER (WHERE ret_20d >= 0.20) AS tail_ge20pct,
       ROUND((100*MAX(ret_20d))::numeric,1) AS best_ret20_pct
FROM mi_ep_missed_outcomes
WHERE setup_at_open IS TRUE AND ret_20d IS NOT NULL
GROUP BY 1,2 HAVING COUNT(*) >= 3 ORDER BY 1, n DESC;

\echo ===Q3_COVERAGE_HONESTY===
SELECT COUNT(*) AS all_rows,
       COUNT(*) FILTER (WHERE setup_at_open IS TRUE)  AS gapped_at_open,
       COUNT(*) FILTER (WHERE setup_at_open IS FALSE) AS did_not_gap,
       COUNT(*) FILTER (WHERE setup_at_open IS NULL)  AS unclassified,
       COUNT(*) FILTER (WHERE setup_at_open IS TRUE AND ret_20d IS NULL) AS gapped_but_no_ret20,
       MIN(alert_date) AS first_date, MAX(alert_date) AS last_date
FROM mi_ep_missed_outcomes;

\echo ===Q4_THE_HTFL_CLASS_ROWS===
SELECT ticker, alert_date, skip_category, skip_reason, ep_score,
       ROUND(open_gap_pct::numeric,1) AS open_gap, ROUND((100*ret_20d)::numeric,1) AS ret20_pct
FROM mi_ep_missed_outcomes
WHERE setup_at_open IS TRUE AND ret_20d >= 0.20
ORDER BY ret_20d DESC LIMIT 40;

\echo ===Q5_DELAYED_LANE_REENTRY_ROWS===
SELECT reentry_shape, COUNT(*) AS n, COUNT(outcome) AS settled,
       MIN(fire_date) AS first, MAX(fire_date) AS last
FROM mi_delayed_entry_trigger GROUP BY reentry_shape ORDER BY n DESC;
