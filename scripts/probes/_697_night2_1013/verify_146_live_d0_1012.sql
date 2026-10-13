-- #146 unpark - VERIFY-LIVE (SELECT-only). Run AFTER the deploy, from the first scan the new code ran on:
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -v d0=2026-10-12 -A -F \$'\\t'" \
--       < scripts/probes/_146_unpark/verify_live.sql
-- d0 = the first scan_date written by the deployed code. Expectations, baseline and stop rule: htf.md change log 2026-10-11 (#146).
--
-- BEFORE this file: prove the RUNNING image carries the change (a stale image fails here, and no SQL below can tell):
--   ssh apollo@87.99.134.162 "docker exec apollo-market-agent python -c 'from agents.market_intelligence import flag_detector as f; print(len(f._TRIGGER_LICENCE), f._TRIGGER_LICENCE)'"
--   must print `3 (('COILED', 'coiled'), ('TIGHTENING', 'tightening'), ('TRIGGERED', 'retrigger'))` - scripts/probes/_146_unpark/verify_deploy.sh runs and asserts it.
--
-- A reading is only evidence if the BROKEN system would read differently:
--   * statement 1 can pass on an empty day, so it is a tripwire, not proof - statement 2 is the proof;
--   * statement 2 judges every raw TRIGGERED row against its own stored 5-day window, so a stamp written from the wrong
--     path (precedence wrong), a read licensed by WATCH alone, or an unstamped row each print VIOLATION;
--   * statement 4 judges the stamp against the breakout TRACKING tables (mi_flag_breaks + mi_htf_breakout_shadow): a
--     COILED parent stamped anything but 'coiled', or a TIGHTENING parent stamped 'retrigger', prints VIOLATION. It reads
--     the stamp, which only the new code writes, so a broken gate cannot satisfy it. (The old statement 4 compared
--     `parent_stage` with the candidate row it was copied from by intraday code #146 never touches - it read 0 on a
--     broken gate, so it could not discriminate.) Its n is small (a break needs an EOD TRIGGERED read the same evening).

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

\echo '== 4. PROOF: the stamp agrees with parent_stage in BOTH breakout tracking tables (a failing row says so in the verdict column; none may)'
-- parent COILED  -> the stamp can only be 'coiled'        (a COILED label is in the window; precedence coiled > tightening > retrigger)
-- parent TIGHTENING -> the stamp is 'coiled' or 'tightening', NEVER 'retrigger'
-- Judged only where the break-date EOD row is a raw TRIGGERED read AND the parent scan sits inside that read's 5-day window.
-- parent_stage is copied from mi_flag_candidates.stage by the intraday scan; the disagreement check below ('does the
-- parent_stage still equal the candidate row it points at') is kept as a side condition, not as the proof.
WITH b AS (
    SELECT 'mi_flag_breaks' AS tbl, id, ticker, break_date, parent_stage, parent_scan_date
    FROM mi_flag_breaks WHERE break_date >= :'d0'::date
    UNION ALL
    SELECT 'mi_htf_breakout_shadow', id, ticker, break_date, parent_stage, parent_scan_date
    FROM mi_htf_breakout_shadow WHERE break_date >= :'d0'::date
), j AS (
    SELECT b.*, c.triggered_from AS bucket, p.stage AS candidate_stage
    FROM b
    LEFT JOIN mi_flag_candidates c
           ON c.ticker = b.ticker AND c.scan_date = b.break_date
          AND c.stage = 'TRIGGERED' AND c.held_from_stage IS NULL
    LEFT JOIN mi_flag_candidates p ON p.ticker = b.ticker AND p.scan_date = b.parent_scan_date
)
SELECT tbl, id, ticker, break_date, parent_stage, parent_scan_date, bucket,
       CASE
         WHEN candidate_stage IS DISTINCT FROM parent_stage
              THEN 'VIOLATION: parent_stage disagrees with the candidate row it points at (' || COALESCE(candidate_stage, 'no row') || ')'
         WHEN bucket IS NULL THEN 'n/a (no raw TRIGGERED EOD read on the break date)'
         WHEN break_date - parent_scan_date > 5 THEN 'n/a (parent scan older than the 5-day window)'
         WHEN parent_stage = 'COILED' AND bucket <> 'coiled'
              THEN 'VIOLATION: COILED parent stamped ' || bucket
         WHEN parent_stage = 'TIGHTENING' AND bucket = 'retrigger'
              THEN 'VIOLATION: TIGHTENING parent stamped retrigger'
         ELSE 'ok'
       END AS verdict
FROM j
WHERE bucket IS NOT NULL OR candidate_stage IS DISTINCT FROM parent_stage
ORDER BY tbl, break_date, ticker;

\echo '== 4b. the same, counted per table (EXPECT violations = 0 and judged_ok >= 1 across the two: a check that judges nothing is a blank, not a pass)'
WITH b AS (
    SELECT 'mi_flag_breaks' AS tbl, ticker, break_date, parent_stage, parent_scan_date
    FROM mi_flag_breaks WHERE break_date >= :'d0'::date
    UNION ALL
    SELECT 'mi_htf_breakout_shadow', ticker, break_date, parent_stage, parent_scan_date
    FROM mi_htf_breakout_shadow WHERE break_date >= :'d0'::date
), j AS (
    SELECT b.*, c.triggered_from AS bucket, p.stage AS candidate_stage
    FROM b
    LEFT JOIN mi_flag_candidates c
           ON c.ticker = b.ticker AND c.scan_date = b.break_date
          AND c.stage = 'TRIGGERED' AND c.held_from_stage IS NULL
    LEFT JOIN mi_flag_candidates p ON p.ticker = b.ticker AND p.scan_date = b.parent_scan_date
), v AS (
    SELECT tbl,
           CASE
             WHEN candidate_stage IS DISTINCT FROM parent_stage THEN 'violation'
             WHEN bucket IS NULL OR break_date - parent_scan_date > 5 THEN 'not_judged'
             WHEN parent_stage = 'COILED' AND bucket <> 'coiled' THEN 'violation'
             WHEN parent_stage = 'TIGHTENING' AND bucket = 'retrigger' THEN 'violation'
             ELSE 'ok'
           END AS verdict
    FROM j
)
SELECT tbl, count(*) AS breaks_since_d0,
       count(*) FILTER (WHERE verdict = 'ok') AS judged_ok,
       count(*) FILTER (WHERE verdict = 'violation') AS violations,
       count(*) FILTER (WHERE verdict = 'not_judged') AS not_judged
FROM v GROUP BY tbl ORDER BY tbl;
