SET default_transaction_read_only = on;
-- advisor 11-27: no LIMIT, 3x volume applied, and the scan_rows=0 base rate on an ordinary day (11-24) for calibration
WITH px AS (
  SELECT c.ticker, c.trade_date, c.open_price, c.volume,
         LAG(c.close) OVER w prev_close, AVG(c.volume) OVER (PARTITION BY c.ticker ORDER BY c.trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) avg20
    FROM mi_daily_closes c WHERE c.trade_date >= DATE '2026-10-20'
  WINDOW w AS (PARTITION BY c.ticker ORDER BY c.trade_date)),
g AS (SELECT p.*, (SELECT count(*) FROM mi_ep_scan_log s WHERE s.ticker=p.ticker AND s.scan_date=p.trade_date) scan_rows
        FROM px p WHERE p.trade_date IN (DATE '2026-11-24', DATE '2026-11-25', DATE '2026-11-27') AND p.prev_close >= 5 AND p.open_price >= 1.09*p.prev_close)
SELECT trade_date, count(*) gappers, count(*) FILTER (WHERE scan_rows=0) unscanned,
       count(*) FILTER (WHERE volume >= 3*avg20) gap_3x, count(*) FILTER (WHERE volume >= 3*avg20 AND scan_rows=0) gap_3x_unscanned
  FROM g GROUP BY 1 ORDER BY 1;
\echo == 11-27 unscanned 3x-volume gappers (the candidates for a real miss)
WITH px AS (
  SELECT c.ticker, c.trade_date, c.open_price, c.volume,
         LAG(c.close) OVER w prev_close, AVG(c.volume) OVER (PARTITION BY c.ticker ORDER BY c.trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) avg20
    FROM mi_daily_closes c WHERE c.trade_date >= DATE '2026-10-20'
  WINDOW w AS (PARTITION BY c.ticker ORDER BY c.trade_date)),
g AS (SELECT p.*, (SELECT count(*) FROM mi_ep_scan_log s WHERE s.ticker=p.ticker AND s.scan_date=p.trade_date) scan_rows
        FROM px p WHERE p.trade_date IN (DATE '2026-11-24', DATE '2026-11-25', DATE '2026-11-27') AND p.prev_close >= 5 AND p.open_price >= 1.09*p.prev_close)
SELECT g.ticker, round((((g.open_price/g.prev_close)-1)*100)::numeric,1) gap, round((g.volume/NULLIF(g.avg20,0))::numeric,1) vol_x, round(g.prev_close::numeric,2) pc
  FROM g WHERE trade_date = DATE '2026-11-27' AND scan_rows = 0 AND volume >= 3*avg20 ORDER BY gap DESC;
