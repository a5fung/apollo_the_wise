-- #697 item 1a VERIFY-LIVE (htf.md change log 2026-10-11). READ-ONLY, one run:
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F \$'\t' -v since=2026-07-01" \
--       < scripts/probes/_697/verify_friday_flag.sql > <out>
-- Per stored Friday list since :since - how many rows are FLAG-sourced. `sources` is JSONB (an array of strings), so the
-- test is the JSONB existence operator `?` (or `sources::text LIKE '%FLAG%'`) - a plain `sources LIKE` errors.
-- Baseline: FLAG rows on the week ending 2026-07-31 and on NO later Friday (the section rendered empty from 2026-08-02).
-- Pass: the week ending 2026-10-16 (or the next Friday whose latest scan holds a COILED / TIGHTENING name) has flag_rows >= 1.
-- That also needs the board: read `board_coiled_tightening` (latest scan on or before the Friday) - an EMPTY board makes
-- flag_rows = 0 correct, not a failure.
SET default_transaction_read_only = on;
\pset footer off
SELECT w.week_ending::text AS week_ending,
       COUNT(*) FILTER (WHERE w.sources ? 'FLAG') AS flag_rows,
       COUNT(*) AS rows,
       (SELECT COUNT(*) FROM mi_flag_candidates c
         WHERE c.scan_date = (SELECT MAX(c2.scan_date) FROM mi_flag_candidates c2 WHERE c2.scan_date <= w.week_ending)
           AND c.stage IN ('COILED', 'TIGHTENING')) AS board_coiled_tightening,
       string_agg(w.ticker, ' ' ORDER BY w.ticker) FILTER (WHERE w.sources ? 'FLAG') AS flag_tickers
FROM mi_weekly_watchlists w
WHERE w.week_ending >= :'since'::date
GROUP BY w.week_ending
ORDER BY w.week_ending;
