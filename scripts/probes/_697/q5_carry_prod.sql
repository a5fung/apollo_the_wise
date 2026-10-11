-- #697 item 2: the production carry query, run read-only for several scan dates.
PREPARE carry(date, int, int) AS WITH scan_days AS (
                    SELECT s.scan_date,
                           ROW_NUMBER() OVER (ORDER BY s.scan_date DESC) AS lag
                    FROM (
                        SELECT DISTINCT scan_date
                        FROM mi_flag_candidates
                        WHERE scan_date < $1::date
                          AND scan_date >= $1::date - make_interval(days => $2::int)
                    ) s
                    WHERE EXISTS (
                        SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = s.scan_date
                    )
                )
                SELECT c.ticker, c.stage, sd.lag::int AS lag
                FROM mi_flag_candidates c
                JOIN scan_days sd ON sd.scan_date = c.scan_date
                WHERE sd.lag <= $3::int
                  AND c.stage IN ('WATCH', 'TIGHTENING', 'COILED', 'TRIGGERED')
                  AND EXISTS (SELECT 1 FROM mi_daily_closes dc WHERE dc.ticker = c.ticker AND dc.trade_date = $1::date);
\echo ## 2026-09-03
EXECUTE carry('2026-09-03', 60, 25);
\echo ## 2026-09-04
EXECUTE carry('2026-09-04', 60, 25);
\echo ## 2026-09-07
EXECUTE carry('2026-09-07', 60, 25);
\echo ## 2026-09-08
EXECUTE carry('2026-09-08', 60, 25);
\echo ## 2026-09-09
EXECUTE carry('2026-09-09', 60, 25);
\echo ## 2026-09-14
EXECUTE carry('2026-09-14', 60, 25);
\echo ## 2026-09-16
EXECUTE carry('2026-09-16', 60, 25);
\echo ## 2026-10-09
EXECUTE carry('2026-10-09', 60, 25);
\echo ## EXPLAIN 2026-10-09
EXPLAIN (ANALYZE, BUFFERS) EXECUTE carry('2026-10-09', 60, 25);
