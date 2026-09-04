-- Ready-to-run pull for the "whole book" side of the 2026-09-04 volume-conviction fix
-- (docs/setups/magna53_ep.md Known Limitations #5). NOT run in this analysis pass — no DB
-- access in that sandbox (no docker/psql/ssh). This is the missing half of the offline
-- evidence: the CONTROL population (candidates the live stack actually scores, not the
-- mcap-excluded cohort) at its TRUE point-in-time tick, so `_volume_percentile`'s honest
-- reading can be computed without the session-only-bars proxy's measured premarket
-- undercount (median ~42%, worse for many names -- see the limitations entry).
--
-- Mirrors scripts/probes/_622sweep_driver.py's tick-selection method (nearest wall-clock
-- tick to 09:31:00 ET, NOT minutes_since_open=1 -- that column floors and can collide two
-- real ticks onto the same value) but as ONE set-based query for the whole 90-day control
-- population instead of a per-ticker Python loop, since this is ~7x the row count.
--
-- Run: ssh apollo@<host> 'docker exec -i apollo-market psql -U <user> -d <db>' \
--        < scripts/probes/_bookvol_control_tick.sql > scripts/probes/_bookvol_control_tick_out.txt
-- Then feed ticker/scan_date/today_volume/adv/rel_volume/market_cap/gap_pct into the SAME
-- rolling20_history()+_volume_percentile() path already used for the excluded cohort
-- (scripts/probes/_622sweep_driver.py / this task's scratch analysis) to get the honest,
-- premarket-inclusive percentile and re-run the admission-flip count on the real population.

\echo === CONTROL_TICK ===
WITH population AS (
    SELECT DISTINCT scan_date, ticker
    FROM mi_ep_scan_log
    WHERE ep_score IS NOT NULL AND scan_date >= CURRENT_DATE - 90
),
ranked AS (
    SELECT
        s.*,  -- (fixed 2026-09-04: p.scan_date/p.ticker duplicated s.* -> ambiguous outer refs)
        ABS(EXTRACT(EPOCH FROM (
            (s.scan_time_et AT TIME ZONE 'America/New_York')
            - (p.scan_date + TIME '09:31:00')
        ))) AS dist_sec,
        ROW_NUMBER() OVER (
            PARTITION BY p.scan_date, p.ticker
            ORDER BY ABS(EXTRACT(EPOCH FROM (
                (s.scan_time_et AT TIME ZONE 'America/New_York')
                - (p.scan_date + TIME '09:31:00')
            ))) ASC, s.scan_time_et ASC
        ) AS rn
    FROM population p
    JOIN mi_ep_scan_log s ON s.ticker = p.ticker AND s.scan_date = p.scan_date
)
SELECT scan_date, ticker, dist_sec, minutes_since_open,
       gap_pct, prev_close, rel_volume, today_volume, adv, market_cap,
       float_shares, ep_score, filter_reason
FROM ranked
WHERE rn = 1
ORDER BY scan_date, ticker;
