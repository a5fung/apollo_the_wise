-- #146 review fix - VERIFY-LIVE for the Friday watchlist listing TRIGGERED names (SELECT-only). Run AFTER the first Friday (18:00 ET job) following the deploy:
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -v since=2026-10-16 -A -F \$'\\t'" \
--       < scripts/probes/_146_unpark/verify_friday.sql
-- since = the first Friday week_ending on or after the deploy. Expectation + stop rule: htf.md change log 2026-10-11 (#146) EXPECT (iv)(f).
--
-- What the BROKEN system would read: the pre-fix Friday query never selected TRIGGERED, so a board name that was TRIGGERED on the list's scan date could not
-- be on the list at all - F1 would show no TRIGGERED row, exactly like a Friday with no breakout. So the proof is POSITIVE: a TRIGGERED candidate row
-- whose board chip says TRIGGERED and names the right path. A Friday with no TRIGGERED name in its latest scan is INCONCLUSIVE, not a pass.
-- The list's scan date is the job's own rule: the latest mi_flag_candidates scan within the 7 days up to the week ending.

\echo '== F1. every Friday board name from a flag source, against its candidate row on the list scan date (verdict starting VIOLATION is a failure)'
WITH w AS (
    SELECT week_ending, ticker, reason_chip,
           (SELECT max(scan_date) FROM mi_flag_candidates
             WHERE scan_date BETWEEN week_ending - 7 AND week_ending) AS list_scan
    FROM mi_weekly_watchlists
    WHERE sources ? 'FLAG' AND week_ending >= :'since'::date
)
SELECT w.week_ending, w.ticker, w.list_scan, c.stage, c.triggered_from, c.held_from_stage,
       left(w.reason_chip, 100) AS chip,
       CASE
         WHEN c.stage = 'TRIGGERED' AND w.reason_chip NOT LIKE '%[TRIGGERED%'
              THEN 'VIOLATION: TRIGGERED on the list scan date but the chip does not say so'
         WHEN c.stage = 'TRIGGERED' AND c.held_from_stage IS NULL AND c.triggered_from IS NOT NULL
              AND w.reason_chip NOT LIKE '%[TRIGGERED · '
                  || (CASE c.triggered_from WHEN 'coiled' THEN 'from COILED' WHEN 'tightening' THEN 'from TIGHTENING' ELSE 're-trigger' END) || '%'
              THEN 'VIOLATION: the chip names a different path than the stamp'
         WHEN c.stage = 'TRIGGERED' AND c.held_from_stage IS NOT NULL AND w.reason_chip NOT LIKE '%[TRIGGERED · held over from yesterday%'
              THEN 'VIOLATION: a held TRIGGERED row is not labelled as held'
         WHEN c.stage = 'TRIGGERED' THEN 'ok'
         ELSE 'n/a (not TRIGGERED on that scan)'
       END AS verdict
FROM w
LEFT JOIN (SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from FROM mi_flag_candidates) c ON c.ticker = w.ticker AND c.scan_date = w.list_scan
ORDER BY w.week_ending, w.ticker;

\echo '== F2. per Friday: flag names on the board / TRIGGERED among them (0 TRIGGERED = inconclusive that Friday, not a pass)'
WITH w AS (
    SELECT week_ending, ticker,
           (SELECT max(scan_date) FROM mi_flag_candidates
             WHERE scan_date BETWEEN week_ending - 7 AND week_ending) AS list_scan
    FROM mi_weekly_watchlists
    WHERE sources ? 'FLAG' AND week_ending >= :'since'::date
)
SELECT w.week_ending, max(w.list_scan) AS list_scan, count(*) AS flag_names_on_board,
       count(*) FILTER (WHERE c.stage = 'TRIGGERED') AS triggered_on_board,
       (SELECT count(*) FROM mi_flag_candidates x
         WHERE x.scan_date = max(w.list_scan) AND x.stage = 'TRIGGERED') AS triggered_in_scan
FROM w
LEFT JOIN (SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from FROM mi_flag_candidates) c ON c.ticker = w.ticker AND c.scan_date = w.list_scan
GROUP BY w.week_ending
ORDER BY w.week_ending;
