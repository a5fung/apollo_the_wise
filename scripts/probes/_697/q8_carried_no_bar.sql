-- #697 item 2 review fix (2026-10-11): which names the carry would score on FROZEN history (no bar on the scan
-- date). (1) rows the OLD system already wrote for a ticker with no bar that (trading-day) night; (2) names the
-- new-rule carry admits on each night 08-04 -> 10-09 that have no bar that night. READ-ONLY, captured once ->
-- q8_carried_no_bar.out. Finding: FBRX (last bar 08-26) 12 nights 08-27 -> 09-14; every other night is empty.
SET default_transaction_read_only = on;
\pset footer off
SELECT 'rows_no_bar' k, c.scan_date::text, c.ticker, c.stage, array_to_string(c.universe_sources, ',') src, c.reason
FROM mi_flag_candidates c
WHERE c.scan_date >= '2026-06-27'
  AND EXISTS (SELECT 1 FROM mi_daily_closes d0 WHERE d0.trade_date = c.scan_date)
  AND NOT EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = c.scan_date AND d.ticker = c.ticker)
ORDER BY c.ticker, c.scan_date;
WITH sess AS (
  SELECT DISTINCT c.scan_date FROM mi_flag_candidates c
  WHERE c.scan_date >= '2026-06-01'
    AND EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = c.scan_date)
),
tgt AS (SELECT scan_date AS d FROM sess WHERE scan_date >= '2026-08-04'),
win AS (
  SELECT t.d, w.scan_date AS sd, w.lag FROM tgt t
  CROSS JOIN LATERAL (
    SELECT x.scan_date, row_number() OVER (ORDER BY x.scan_date DESC) AS lag
    FROM (SELECT s.scan_date FROM sess s WHERE s.scan_date < t.d ORDER BY s.scan_date DESC LIMIT 25) x
  ) w
),
cand AS (
  SELECT w.d, c.ticker, bool_or(w.lag <= 5) AS short_ok,
         bool_or(c.stage IN ('TIGHTENING','COILED','TRIGGERED')) AS long_ok,
         (array_agg(c.stage || '@' || c.scan_date::text ORDER BY c.scan_date DESC))[1] AS last_stage
  FROM win w JOIN mi_flag_candidates c ON c.scan_date = w.sd
  WHERE c.stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED')
  GROUP BY w.d, c.ticker
)
SELECT 'carried_no_bar' k, x.d::text, x.ticker, x.last_stage, CASE WHEN x.short_ok THEN 'short' ELSE 'long' END,
       (SELECT MAX(d.trade_date)::text FROM mi_daily_closes d WHERE d.ticker = x.ticker AND d.trade_date <= x.d) AS last_bar
FROM cand x
WHERE (x.short_ok OR x.long_ok)
  AND NOT EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = x.d AND d.ticker = x.ticker)
ORDER BY x.ticker, x.d;
