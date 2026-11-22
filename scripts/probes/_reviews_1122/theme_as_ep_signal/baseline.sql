SET default_transaction_read_only = on;
\echo === Q0 composition: HIGH alerts since 2026-06-02 by in_active_theme and month, with settled-outcome counts
SELECT to_char(a.alert_date,'YYYY-MM') AS mon, a.in_active_theme, COUNT(*) AS n_alerts,
       COUNT(o.fwd_10d_pct) AS n_settled_10d
FROM mi_ep_alerts a
LEFT JOIN mi_ep_scan_outcomes o ON o.ticker=a.ticker AND o.scan_date=a.alert_date
WHERE a.score_tier='HIGH' AND a.alert_date >= '2026-06-02'
GROUP BY 1,2 ORDER BY 1,2;
\echo === Q1 predicate (review's own): count
SELECT COUNT(*) AS predicate_count FROM mi_ep_alerts a
JOIN mi_ep_scan_outcomes o ON o.ticker=a.ticker AND o.scan_date=a.alert_date
WHERE a.score_tier='HIGH' AND o.fwd_10d_pct IS NOT NULL AND a.alert_date >= '2026-06-02';
\echo === Q2 benchmark presence (SPY/QQQ/IWM rows in mi_daily_closes since 2026-05-01)
SELECT ticker, COUNT(*) n, MIN(trade_date) mn, MAX(trade_date) mx FROM mi_daily_closes
WHERE ticker IN ('SPY','QQQ','IWM') AND trade_date >= '2026-05-01' GROUP BY 1 ORDER BY 1;
\echo === Q3 per-alert rows: close-to-close 10d/20d vs SPY and QQQ, plus the high-watermark fwd_10d (columns: ticker|alert_date|in_active_theme|hw5|hw10|c10|c20|spy10|spy20|qqq10|qqq20)
WITH cal AS (
  SELECT trade_date, ROW_NUMBER() OVER (ORDER BY trade_date) AS idx
  FROM (SELECT DISTINCT trade_date FROM mi_daily_closes WHERE ticker='SPY' AND trade_date >= '2026-05-01') s
), al AS (
  SELECT DISTINCT ON (a.ticker, a.alert_date) a.ticker, a.alert_date, a.in_active_theme
  FROM mi_ep_alerts a
  WHERE a.score_tier='HIGH' AND a.alert_date >= '2026-06-02'
  ORDER BY a.ticker, a.alert_date, a.id
), al2 AS (
  SELECT al.*, c0.idx AS i0 FROM al JOIN cal c0 ON c0.trade_date = al.alert_date
), px AS (
  SELECT x.ticker, x.alert_date, x.in_active_theme, x.i0,
    (SELECT close FROM mi_daily_closes d WHERE d.ticker=x.ticker AND d.trade_date=x.alert_date) AS p0,
    (SELECT d.close FROM mi_daily_closes d JOIN cal c ON c.trade_date=d.trade_date WHERE d.ticker=x.ticker AND c.idx=x.i0+10) AS p10,
    (SELECT d.close FROM mi_daily_closes d JOIN cal c ON c.trade_date=d.trade_date WHERE d.ticker=x.ticker AND c.idx=x.i0+20) AS p20
  FROM al2 x
), bm AS (
  SELECT t.tk,
    c0.trade_date AS d0,
    (SELECT close FROM mi_daily_closes WHERE ticker=t.tk AND trade_date=c0.trade_date) AS b0,
    (SELECT d.close FROM mi_daily_closes d JOIN cal c ON c.trade_date=d.trade_date WHERE d.ticker=t.tk AND c.idx=c0.idx+10) AS b10,
    (SELECT d.close FROM mi_daily_closes d JOIN cal c ON c.trade_date=d.trade_date WHERE d.ticker=t.tk AND c.idx=c0.idx+20) AS b20
  FROM (VALUES ('SPY'),('QQQ')) t(tk) CROSS JOIN cal c0
)
SELECT px.ticker, px.alert_date, COALESCE(px.in_active_theme::text,'null'),
  o.fwd_5d_pct, o.fwd_10d_pct,
  ROUND((100*(px.p10/px.p0-1))::numeric,2), ROUND((100*(px.p20/px.p0-1))::numeric,2),
  ROUND((100*(s.b10/s.b0-1))::numeric,2), ROUND((100*(s.b20/s.b0-1))::numeric,2),
  ROUND((100*(q.b10/q.b0-1))::numeric,2), ROUND((100*(q.b20/q.b0-1))::numeric,2)
FROM px
LEFT JOIN mi_ep_scan_outcomes o ON o.ticker=px.ticker AND o.scan_date=px.alert_date
LEFT JOIN bm s ON s.tk='SPY' AND s.d0=px.alert_date
LEFT JOIN bm q ON q.tk='QQQ' AND q.d0=px.alert_date
ORDER BY px.alert_date, px.ticker;
