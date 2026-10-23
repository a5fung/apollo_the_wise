\pset pager off
-- #697 phase 1b (read-only): rows JUST BELOW vs JUST ABOVE the 20-day average. The kill is a pure threshold, so names a hair
-- either side are alike; if their next 30 days look alike, the threshold separates nothing at the margin. Rows that an
-- EARLIER gate already killed (base age, base low) are excluded; mature = scan_date <= 2026-09-22.
WITH r AS (
  SELECT f.ticker, f.scan_date, f.pivot_high_date, f.base_high, f.base_low, f.stage, d.close, f.sma_20,
         d.close / f.sma_20 - 1 AS m
  FROM mi_flag_candidates f JOIN mi_daily_closes d ON d.ticker = f.ticker AND d.trade_date = f.scan_date
  WHERE f.sma_20 > 0 AND f.base_high IS NOT NULL AND f.base_low IS NOT NULL AND f.scan_date <= '2026-09-22'
    AND coalesce(f.reason,'') !~ '^base_age_[0-9]+_over' AND coalesce(f.reason,'') !~ 'below_base_low_close'
    AND f.held_from_stage IS NULL AND d.close / f.sma_20 - 1 BETWEEN -0.02 AND 0.02
), o AS (
  SELECT r.*,
    (SELECT min(d.trade_date) FROM mi_daily_closes d WHERE d.ticker=r.ticker AND d.trade_date > r.scan_date
       AND d.trade_date <= r.scan_date + 30 AND d.close > r.base_high) bo,
    (SELECT min(d.trade_date) FROM mi_daily_closes d WHERE d.ticker=r.ticker AND d.trade_date > r.scan_date
       AND d.trade_date <= r.scan_date + 30 AND d.close < r.base_low) fl,
    (r.close - r.base_low) / nullif(r.base_high - r.base_low, 0) AS pos
  FROM r
)
SELECT CASE WHEN m < -0.01 THEN 'a below by 1-2%' WHEN m < -0.005 THEN 'b below by 0.5-1%' WHEN m < 0 THEN 'c below by < 0.5%'
            WHEN m < 0.005 THEN 'd above by < 0.5%' WHEN m < 0.01 THEN 'e above by 0.5-1%' ELSE 'f above by 1-2%' END band,
  count(*) n, count(DISTINCT (ticker, pivot_high_date)) bases,
  round(avg(pos)::numeric, 2) avg_position_in_base,
  round(100.0*count(*) FILTER (WHERE bo IS NOT NULL AND (fl IS NULL OR bo < fl))/count(*),1) pct_broke_out_first,
  round(100.0*count(*) FILTER (WHERE fl IS NOT NULL AND (bo IS NULL OR fl < bo))/count(*),1) pct_failed_first
FROM o GROUP BY 1 ORDER BY 1;
