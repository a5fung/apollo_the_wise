-- #697 item 4 (htf_scope G3) - LIVE VERIFY of mi_flag_candidates.post_breakout_from / days_since_breakout. READ-ONLY.
--
--   psql "$DATABASE_URL" -v d0=2026-10-19 -v since=2025-08-01 -f scripts/probes/_697_item4/verify_live.sql
--
--   d0     the FIRST scan_date written by the deployed code (the first 17:25 ET scan after the deploy)
--   since  a bar lower bound at least 40 sessions before the oldest pole a stamp can cite (a year back is plenty)
--
-- WHAT IT CHECKS, and why the broken system cannot pass it: statement 2 RE-DERIVES the stamp for every scanned row
-- from mi_daily_closes alone, in SQL, independently of flag_detector._post_breakout_state, and compares the two in BOTH
-- directions. A detector that never stamps fails on every row the SQL says should be stamped; a detector that stamps
-- everything fails on every row the SQL says should be NULL. The statement's own correctness is shown by
-- scripts/probes/_697_item4/dryrun_verify_sql.py: this exact text, run in DuckDB over the 6,346 pivot-anchored rows of the
-- replayed corpus + capture (every replay session after the first), agrees with the detector on every one, and flags
-- every deliberate tamper.
--
-- THE RULE IT RE-DERIVES (docs/setups/htf.md, change log 2026-10-16): a row is stamped when (a) EVENT - the ticker's
-- pivot moved to a LATER bar than its previous stored pivot, that old pole top is <= 25 sessions back, the pole is a pole
-- (high / lowest low of the 40 sessions ending at it >= 1.90) and some bar from the 4th session after the top up to the
-- session before the scan CLOSED above the top's high; or (b) CARRY - the previous stored stamp's pole passes the same
-- test and its first such close is <= 25 sessions back. days_since_breakout = scan session - that first-close session.
-- The event wins over a carry. Windows are the detector's: the previous pivot / stamp come from the last stored row within
-- 40 calendar days.

-- ── 1. write health: rows per scan, how many stamped, how many are day-1 (a fresh re-anchor) ───────────────────────────
-- A scan that wrote ~0 rows is the deploy-order failure (the INSERT names columns the table lacks) - compare with the
-- nights before d0 (same query, an earlier d0): ~540 rows/night.
SELECT scan_date,
       count(*)                                         AS rows_written,
       count(post_breakout_from)                        AS stamped,
       count(*) FILTER (WHERE days_since_breakout = 1)  AS day_1_rows
FROM mi_flag_candidates
WHERE scan_date >= :'d0'::date
GROUP BY 1
ORDER BY 1;

-- ── 2. the independent re-derivation, compared both ways (one row per scanned row that reached the pivot anchor) ───────
-- Prints every row where the stored pair differs from the re-derived pair (a VIOLATION), then the totals.
WITH cand AS (
    SELECT ticker, scan_date, pivot_high_date AS pivot_today,
           post_breakout_from AS got_from, days_since_breakout AS got_days
    FROM mi_flag_candidates
    WHERE scan_date >= :'d0'::date AND pivot_high_date IS NOT NULL
),
prior_pivot AS (       -- what db.get_yesterday_flag_pivots hands the detector
    SELECT DISTINCT ON (c.ticker, c.scan_date) c.ticker, c.scan_date, p.pivot_high_date AS old_pivot
    FROM cand c
    JOIN mi_flag_candidates p ON p.ticker = c.ticker AND p.scan_date < c.scan_date
                             AND p.scan_date >= c.scan_date - 40
                             AND p.pivot_high_date IS NOT NULL AND p.pivot_high_price IS NOT NULL
    ORDER BY c.ticker, c.scan_date, p.scan_date DESC
),
prior_stamp AS (       -- what db.get_flag_post_breakout_carry hands it
    SELECT DISTINCT ON (c.ticker, c.scan_date) c.ticker, c.scan_date, p.post_breakout_from AS carried
    FROM cand c
    JOIN mi_flag_candidates p ON p.ticker = c.ticker AND p.scan_date < c.scan_date
                             AND p.scan_date >= c.scan_date - 40
                             AND p.post_breakout_from IS NOT NULL
    ORDER BY c.ticker, c.scan_date, p.scan_date DESC
),
claim AS (             -- every pole top a row could cite: where the pivot moved from, and the stamp carried in
    SELECT c.ticker, c.scan_date, pp.old_pivot AS pole_date, 'event' AS kind
    FROM cand c JOIN prior_pivot pp ON pp.ticker = c.ticker AND pp.scan_date = c.scan_date
    WHERE c.pivot_today > pp.old_pivot
    UNION ALL
    SELECT c.ticker, c.scan_date, ps.carried, 'carry'
    FROM cand c JOIN prior_stamp ps ON ps.ticker = c.ticker AND ps.scan_date = c.scan_date
),
bars AS (              -- one session index per ticker (only differences of it are used); only tickers that cite a pole
    SELECT ticker, trade_date, high_price, low_price, close,
           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date) AS n
    FROM mi_daily_closes
    WHERE trade_date >= :'since'::date AND ticker IN (SELECT ticker FROM claim)
),
judged AS (
    SELECT cl.ticker, cl.scan_date, cl.kind, cl.pole_date, bp.n AS pole_n, bt.n AS today_n,
           bp.high_price AS pole_high,
           (SELECT min(x.low_price) FROM bars x
             WHERE x.ticker = cl.ticker AND x.n BETWEEN bp.n - 39 AND bp.n) AS pole_low,
           (SELECT min(x.n) FROM bars x
             WHERE x.ticker = cl.ticker AND x.n >= bp.n + 4 AND x.n < bt.n
               AND x.close > bp.high_price) AS b_n
    FROM claim cl
    JOIN bars bp ON bp.ticker = cl.ticker AND bp.trade_date = cl.pole_date
    JOIN bars bt ON bt.ticker = cl.ticker AND bt.trade_date = cl.scan_date
),
expected AS (
    SELECT ticker, scan_date, kind, pole_date,
           CASE WHEN pole_low > 0 AND pole_high / pole_low >= 1.90 AND b_n IS NOT NULL
                     AND ((kind = 'event' AND today_n - pole_n BETWEEN 1 AND 25)
                          OR (kind = 'carry' AND today_n - b_n <= 25))
                THEN today_n - b_n END AS exp_days
    FROM judged
),
compare AS (
    SELECT c.ticker, c.scan_date, c.got_from, c.got_days,
           COALESCE(ev.pole_date, ca.pole_date) AS exp_from,
           COALESCE(ev.exp_days, ca.exp_days)   AS exp_days
    FROM cand c
    LEFT JOIN expected ev ON ev.ticker = c.ticker AND ev.scan_date = c.scan_date AND ev.kind = 'event' AND ev.exp_days IS NOT NULL
    LEFT JOIN expected ca ON ca.ticker = c.ticker AND ca.scan_date = c.scan_date AND ca.kind = 'carry' AND ca.exp_days IS NOT NULL
),
verdict AS (
    SELECT *,
           CASE WHEN exp_days IS NULL AND got_days IS NULL AND got_from IS NULL THEN 'ok_null'
                WHEN exp_days IS NOT NULL AND got_days = exp_days AND got_from = exp_from THEN 'ok_stamped'
                WHEN exp_days IS NOT NULL AND got_days IS NULL THEN 'VIOLATION_missing_stamp'
                WHEN exp_days IS NULL THEN 'VIOLATION_unsupported_stamp'
                ELSE 'VIOLATION_wrong_value' END AS verdict
    FROM compare
)
SELECT verdict, count(*) AS rows, min(scan_date) AS first_scan, max(scan_date) AS last_scan,
       string_agg(DISTINCT CASE WHEN verdict LIKE 'VIOLATION%' THEN ticker END, ',') AS tickers_in_violation
FROM verdict
GROUP BY verdict
ORDER BY verdict;
-- READ IT: `ok_stamped` >= 1 is the POSITIVE evidence (a stamp was written AND matches the bars); zero VIOLATION_* rows.
-- `ok_stamped` = 0 over the whole window is INCONCLUSIVE (no breakout re-anchor happened), not a pass.

-- ── 3. shape: both columns move together and stay inside the horizon ───────────────────────────────────────────────────
SELECT count(*) AS violations
FROM mi_flag_candidates
WHERE scan_date >= :'d0'::date
  AND ((post_breakout_from IS NULL) <> (days_since_breakout IS NULL)
       OR days_since_breakout NOT BETWEEN 1 AND 25
       OR post_breakout_from >= scan_date);
