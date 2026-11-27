SET default_transaction_read_only = on;
\echo == A. #736 missed-gapper read: stocks that opened >= 9% above their 11-25 close on 11-27, volume >= 3x 20d avg, and whether the EP scan logged them
WITH px AS (
  SELECT c.ticker, c.trade_date, c.open_price, c.close, c.volume,
         LAG(c.close) OVER w prev_close, AVG(c.volume) OVER (PARTITION BY c.ticker ORDER BY c.trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) avg20
    FROM mi_daily_closes c WHERE c.trade_date >= DATE '2026-10-20'
  WINDOW w AS (PARTITION BY c.ticker ORDER BY c.trade_date))
SELECT p.ticker, round(((p.open_price/p.prev_close)-1)*100,1) gap_open, round((p.volume/NULLIF(p.avg20,0))::numeric,1) vol_x,
       round(((p.close/p.prev_close)-1)*100,1) day_chg, round(p.prev_close::numeric,2) prev_close,
       (SELECT count(*) FROM mi_ep_scan_log s WHERE s.ticker=p.ticker AND s.scan_date=DATE '2026-11-27') scan_rows,
       (SELECT count(*) FROM mi_ep_alerts a WHERE a.ticker=p.ticker AND a.alert_date=DATE '2026-11-27') alerts
  FROM px p WHERE p.trade_date = DATE '2026-11-27' AND p.prev_close > 0 AND p.open_price >= 1.09*p.prev_close AND p.open_price >= 5
 ORDER BY gap_open DESC LIMIT 40;
\echo == B. #728 stop moves today (mechanism) and retries
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI') t, event_type, left(summary,140), left(detail::text,160)
  FROM mi_audit_log WHERE created_at >= '2026-11-27 09:00-05' AND (event_type LIKE 'stop_%' OR detail::text ILIKE '%price_only_replace%') ORDER BY created_at;
\echo == C. #735 COT news watch rows
SELECT count(*), min(event_date), max(event_date), count(*) FILTER (WHERE verdict IS NOT NULL) judged, max(updated_at) FROM mi_cot_news_watch;
SELECT event_date, event_type, market, direction, left(read,80), forecast_seen_at FROM mi_cot_news_watch ORDER BY event_date, market LIMIT 12;
\echo == D. COT alerts today + news-watch errors in audit
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI') t, event_type, left(summary,160) FROM mi_audit_log WHERE created_at >= '2026-11-27 17:00-05' AND (event_type ILIKE '%cot%') ORDER BY created_at LIMIT 20;
