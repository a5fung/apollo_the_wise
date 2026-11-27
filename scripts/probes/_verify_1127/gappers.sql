SET default_transaction_read_only = on;
\echo == A. #736 missed-gapper read: stocks that opened >= 9% above their 11-25 close on 11-27, volume >= 3x 20d avg, and whether the EP scan logged them
WITH px AS (
  SELECT c.ticker, c.trade_date, c.open_price, c.close, c.volume,
         LAG(c.close) OVER w prev_close, AVG(c.volume) OVER (PARTITION BY c.ticker ORDER BY c.trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) avg20
    FROM mi_daily_closes c WHERE c.trade_date >= DATE '2026-10-20'
  WINDOW w AS (PARTITION BY c.ticker ORDER BY c.trade_date))
SELECT p.ticker, round((((p.open_price/p.prev_close)-1)*100)::numeric,1) gap_open, round((p.volume/NULLIF(p.avg20,0))::numeric,1) vol_x,
       round((((p.close/p.prev_close)-1)*100)::numeric,1) day_chg, round(p.prev_close::numeric,2) prev_close,
       (SELECT count(*) FROM mi_ep_scan_log s WHERE s.ticker=p.ticker AND s.scan_date=DATE '2026-11-27') scan_rows,
       (SELECT count(*) FROM mi_ep_alerts a WHERE a.ticker=p.ticker AND a.alert_date=DATE '2026-11-27') alerts
  FROM px p WHERE p.trade_date = DATE '2026-11-27' AND p.prev_close > 0 AND p.open_price >= 1.09*p.prev_close AND p.open_price >= 5
 ORDER BY gap_open DESC LIMIT 40;
