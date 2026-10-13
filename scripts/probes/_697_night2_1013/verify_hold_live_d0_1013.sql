-- #697 item 5 (2026-10-11): VERIFY-LIVE for the one-day hysteresis hold. READ-ONLY.
--   psql ... -v d0=2026-10-12 -f verify_hold_live.sql      (d0 = the first scan date written by the deployed code)
-- For every row on or after d0, its "yesterday" is what the scan itself reads: the ticker's most recent prior row
-- within 5 calendar days (db.get_yesterday_flag_state) — here LAG() over the ticker's rows. A hold is `held_from_stage IS NOT NULL`.
--   violators   own row is a hold AND yesterday was a hold            -> the BROKEN code writes these (24 in the 60 scan days to
--                                                                        2026-10-09, ~0.4 a night); the fix writes 0. WOULD-FAIL-IF > 0.
--   fingerprint own row is NOT a hold, yesterday WAS, and the stage fell -> a downgrade the old code would have held AGAIN. Only the
--                                                                        fixed code writes it (the old code: 0 by construction).
--   first_holds own row is a hold, yesterday was not                    -> the documented one-night hold still works.
--   after_hold  rows whose yesterday was a hold (the denominator)
SET statement_timeout = '30s';                  -- a probe must never be able to run away on prod
WITH w AS (
    SELECT ticker, scan_date, stage, held_from_stage,
           CASE stage WHEN 'WATCH' THEN 1 WHEN 'TIGHTENING' THEN 2 WHEN 'COILED' THEN 3 WHEN 'TRIGGERED' THEN 4 ELSE 0 END AS rk,
           LAG(scan_date)       OVER t AS pdate,
           LAG(stage)           OVER t AS pstage,
           LAG(held_from_stage) OVER t AS pheld,
           LAG(CASE stage WHEN 'WATCH' THEN 1 WHEN 'TIGHTENING' THEN 2 WHEN 'COILED' THEN 3 WHEN 'TRIGGERED' THEN 4 ELSE 0 END) OVER t AS prk
    FROM mi_flag_candidates
    WHERE scan_date >= :'d0'::date - 7          -- a row's "yesterday" is at most 5 days back; 7 covers the first row of the window
    WINDOW t AS (PARTITION BY ticker ORDER BY scan_date)
),
paired AS (
    SELECT * FROM w WHERE scan_date >= :'d0'::date AND pdate IS NOT NULL AND scan_date - pdate <= 5
)
SELECT count(*) FILTER (WHERE pheld IS NOT NULL)                                          AS after_hold,
       count(*) FILTER (WHERE held_from_stage IS NOT NULL AND pheld IS NOT NULL)          AS violators,
       count(*) FILTER (WHERE held_from_stage IS NULL AND pheld IS NOT NULL AND rk < prk
                          AND stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED'))       AS fingerprint,
       count(*) FILTER (WHERE held_from_stage IS NOT NULL AND pheld IS NULL)              AS first_holds,
       count(DISTINCT scan_date)                                                          AS scan_dates
FROM paired;

-- Statement 2: the number the scan LOGS as `holds_carried=K` (flag_detector.run_flag_scan: len of the holds set from db.get_yesterday_flag_state) —
-- EVERY ticker whose latest prior row (< scan_date, >= scan_date - 5) is a hold, whether or not it was scored that night, so it is
-- NOT `after_hold` above (which only counts tickers that got a row on the date). Compare per date with
--   docker logs <market-agent> | grep "flag_scan <date>: scoring"      -> `... | holds_carried=K`
-- `d0` itself is always listed (UNION), so the K a scan WILL log can be read BEFORE that scan has run (-v d0=<next scan date>).
WITH d AS (
    SELECT :'d0'::date AS scan_date
    UNION
    SELECT DISTINCT scan_date FROM mi_flag_candidates WHERE scan_date >= :'d0'::date
)
SELECT d.scan_date, count(*) FILTER (WHERE p.held_from_stage IS NOT NULL) AS expected_holds_carried
FROM d
CROSS JOIN LATERAL (
    SELECT DISTINCT ON (ticker) ticker, held_from_stage FROM mi_flag_candidates
    WHERE scan_date < d.scan_date AND scan_date >= d.scan_date - 5
    ORDER BY ticker, scan_date DESC
) p
GROUP BY d.scan_date ORDER BY d.scan_date;
