-- forward read for pushable-or-better rows: next 10 / 20 sessions from mi_daily_closes
WITH days AS (SELECT DISTINCT scan_date FROM mi_flag_candidates ORDER BY scan_date DESC LIMIT 60),
r AS (SELECT id, ticker, scan_date, stage, base_high, pivot_high_price, base_low
      FROM mi_flag_candidates WHERE scan_date IN (SELECT scan_date FROM days) AND stage IN ('TIGHTENING','COILED','TRIGGERED')),
f AS (SELECT r.id, d.trade_date, d.close, d.high_price, d.low_price,
             ROW_NUMBER() OVER (PARTITION BY r.id ORDER BY d.trade_date) n
      FROM r JOIN mi_daily_closes d ON d.ticker=r.ticker AND d.trade_date>r.scan_date),
c0 AS (SELECT r.id, d.close close0 FROM r JOIN mi_daily_closes d ON d.ticker=r.ticker AND d.trade_date=r.scan_date)
SELECT r.ticker, r.scan_date, r.stage, r.base_high, r.pivot_high_price, r.base_low, c0.close0,
  COUNT(f.n) FILTER (WHERE f.n<=10) n10,
  MAX(f.close) FILTER (WHERE f.n<=10) maxc10, MAX(f.high_price) FILTER (WHERE f.n<=10) maxh10, MIN(f.low_price) FILTER (WHERE f.n<=10) minl10,
  MIN(f.trade_date) FILTER (WHERE f.n<=10 AND f.close>r.base_high) first_close_over_bh10,
  MIN(f.trade_date) FILTER (WHERE f.n<=10 AND f.close>r.pivot_high_price) first_close_over_pole10,
  MIN(f.trade_date) FILTER (WHERE f.n<=10 AND f.close<r.base_low) first_close_under_bl10,
  MAX(f.close) FILTER (WHERE f.n=20) c20, COUNT(f.n) FILTER (WHERE f.n<=20) n20
FROM r LEFT JOIN f ON f.id=r.id LEFT JOIN c0 ON c0.id=r.id
GROUP BY r.ticker, r.scan_date, r.stage, r.base_high, r.pivot_high_price, r.base_low, c0.close0
ORDER BY r.ticker, r.scan_date;
