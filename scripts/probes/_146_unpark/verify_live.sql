-- #146 unpark - VERIFY-LIVE (SELECT-only). Run AFTER the deploy, from the first scan the new code ran on:
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -v d0=2026-10-12 -A -F \$'\\t'" \
--       < scripts/probes/_146_unpark/verify_live.sql
-- d0 = the first scan_date written by the deployed code. Expectations, baseline and stop rule: htf.md change log 2026-10-11 (#146).
--
-- A reading is only evidence if the BROKEN system would read differently:
--   * statement 1 can pass on an empty day, so it is a tripwire, not proof - statement 2 is the proof;
--   * statement 2 judges every raw TRIGGERED row against its own stored 5-day window, so a stamp written from the wrong
--     path (precedence wrong), a read licensed by WATCH alone, or an unstamped row each print VIOLATION.

\echo '== 1. stamp tripwire per scan date (unstamped raw reads, stamped holds, stamped non-TRIGGERED rows must all be 0)'
SELECT scan_date,
       count(*) FILTER (WHERE stage = 'TRIGGERED' AND held_from_stage IS NULL) AS raw_triggered,
       count(*) FILTER (WHERE stage = 'TRIGGERED' AND held_from_stage IS NULL AND triggered_from IS NULL) AS unstamped_raw,
       count(*) FILTER (WHERE stage = 'TRIGGERED' AND held_from_stage IS NOT NULL AND triggered_from IS NOT NULL) AS stamped_hold,
       count(*) FILTER (WHERE stage <> 'TRIGGERED' AND triggered_from IS NOT NULL) AS stamped_non_triggered
FROM mi_flag_candidates
WHERE scan_date >= :'d0'::date
GROUP BY scan_date
ORDER BY scan_date;

\echo '== 2. PROOF: every raw TRIGGERED read since d0 against its own stored 5-day window'
WITH r AS (
    SELECT ticker, scan_date, triggered_from
    FROM mi_flag_candidates
    WHERE stage = 'TRIGGERED' AND held_from_stage IS NULL AND scan_date >= :'d0'::date
), w AS (
    SELECT r.ticker, r.scan_date, r.triggered_from,
           COALESCE(array_agg(p.stage ORDER BY p.scan_date) FILTER (WHERE p.stage IS NOT NULL), '{}') AS labels
    FROM r
    LEFT JOIN mi_flag_candidates p
           ON p.ticker = r.ticker AND p.scan_date < r.scan_date AND p.scan_date >= r.scan_date - 5
    GROUP BY r.ticker, r.scan_date, r.triggered_from
)
SELECT ticker, scan_date, triggered_from, labels,
       CASE
         WHEN triggered_from IS NULL THEN 'VIOLATION: unstamped'
         WHEN triggered_from NOT IN ('coiled', 'tightening', 'retrigger') THEN 'VIOLATION: unknown bucket'
         WHEN triggered_from = 'tightening' AND 'COILED' = ANY(labels) THEN 'VIOLATION: precedence (a COILED label is in the window)'
         WHEN triggered_from = 'tightening' AND NOT ('TIGHTENING' = ANY(labels)) THEN 'VIOLATION: no TIGHTENING label licenses it'
         WHEN triggered_from = 'retrigger' AND ('COILED' = ANY(labels) OR 'TIGHTENING' = ANY(labels)) THEN 'VIOLATION: precedence (COILED/TIGHTENING in window)'
         WHEN triggered_from = 'retrigger' AND NOT ('TRIGGERED' = ANY(labels)) THEN 'VIOLATION: no earlier TRIGGERED label'
         WHEN triggered_from = 'coiled' AND NOT ('COILED' = ANY(labels)) THEN 'ok (COILED the same day - not checkable from labels; historically 2 of 42)'
         ELSE 'ok'
       END AS verdict
FROM w
ORDER BY scan_date, ticker;

\echo '== 3. raw TRIGGERED reads per bucket since d0 (EXPECT: coiled keeps its ~1 per 15 sessions; tightening/retrigger are the new ones)'
SELECT triggered_from AS bucket, count(*) AS reads, min(scan_date) AS first_seen, max(scan_date) AS last_seen
FROM mi_flag_candidates
WHERE stage = 'TRIGGERED' AND held_from_stage IS NULL AND scan_date >= :'d0'::date
GROUP BY triggered_from
ORDER BY 1;

\echo '== 4. the breakout tracking tables still agree with the candidate rows they point at (mismatches must be 0)'
SELECT count(*) AS shadow_rows_since_d0,
       count(*) FILTER (WHERE p.stage IS NOT DISTINCT FROM s.parent_stage) AS parent_stage_matches,
       count(*) FILTER (WHERE p.stage IS DISTINCT FROM s.parent_stage) AS parent_stage_mismatches
FROM mi_htf_breakout_shadow s
LEFT JOIN mi_flag_candidates p ON p.ticker = s.ticker AND p.scan_date = s.parent_scan_date
WHERE s.break_date >= :'d0'::date;
