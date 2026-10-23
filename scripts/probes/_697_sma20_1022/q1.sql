\pset pager off
-- #697 SMA20-kill read, phase 1 (read-only). Every stored row the SMA20 rule invalidated, with its depth below the 20-day
-- average parsed from the reason, and what the base did over the next 30 calendar days (~20 sessions): first close above
-- the base high (broke out) vs first close below the base low (failed). Mature = scan_date <= 2026-09-22.
WITH k AS (
  SELECT ticker, scan_date, pivot_high_date, base_high, base_low, base_age,
         substring(reason from '^close_([0-9.]+)_below')::float / substring(reason from 'sma20_([0-9.]+)$')::float - 1 AS m
  FROM mi_flag_candidates
  WHERE reason ~ '^close_[0-9.]+_below_sma20_[0-9.]+$' AND base_high IS NOT NULL AND base_low IS NOT NULL
), ref AS (   -- reference: the first WATCH-or-better row of each base (never a hold), same outcome window
  SELECT DISTINCT ON (ticker, pivot_high_date) ticker, scan_date, pivot_high_date, base_high, base_low, base_age, NULL::float AS m
  FROM mi_flag_candidates
  WHERE stage IN ('WATCH','TIGHTENING','COILED') AND held_from_stage IS NULL AND base_high IS NOT NULL AND base_low IS NOT NULL
  ORDER BY ticker, pivot_high_date, scan_date
), u AS (
  SELECT 'kill' src, * FROM k UNION ALL SELECT 'ref', * FROM ref
), o AS (
  SELECT u.*,
    (SELECT min(d.trade_date) FROM mi_daily_closes d WHERE d.ticker=u.ticker AND d.trade_date > u.scan_date
       AND d.trade_date <= u.scan_date + 30 AND d.close > u.base_high) bo,
    (SELECT min(d.trade_date) FROM mi_daily_closes d WHERE d.ticker=u.ticker AND d.trade_date > u.scan_date
       AND d.trade_date <= u.scan_date + 30 AND d.close < u.base_low) fl
  FROM u WHERE u.scan_date <= '2026-09-22'
), b AS (
  SELECT *, CASE WHEN src='ref' THEN '0 reference: first WATCH+ row of each base'
                 WHEN m > -0.005 THEN '1 kill, under the 20-day by < 0.5%'
                 WHEN m > -0.01 THEN '2 kill, 0.5-1%'
                 WHEN m > -0.02 THEN '3 kill, 1-2%'
                 ELSE '4 kill, 2% or more' END bucket
  FROM o
)
SELECT bucket, count(*) n, count(DISTINCT (ticker, pivot_high_date)) bases,
  round(100.0*count(*) FILTER (WHERE bo IS NOT NULL AND (fl IS NULL OR bo < fl))/count(*),1) pct_broke_out_first,
  round(100.0*count(*) FILTER (WHERE fl IS NOT NULL AND (bo IS NULL OR fl < bo))/count(*),1) pct_failed_first,
  round(100.0*count(*) FILTER (WHERE bo IS NULL AND fl IS NULL)/count(*),1) pct_neither
FROM b GROUP BY bucket ORDER BY bucket;
