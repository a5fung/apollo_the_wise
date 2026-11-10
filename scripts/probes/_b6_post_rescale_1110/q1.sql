SET default_transaction_read_only = on;
SELECT max(trade_date) AS last_bar FROM mi_daily_closes;
WITH c AS (
  SELECT m.ticker, m.alert_date,
    CASE WHEN m.alert_date >= '2026-08-22' THEN 'post' ELSE 'pre' END AS era,
    (SELECT string_agg(DISTINCT a.detail::jsonb->>'reason', ';') FROM mi_audit_log a
      WHERE a.event_type = 'catalyst_earnings_revenue_weak_downgrade'
        AND a.detail LIKE '%"ticker": "' || m.ticker || '"%'
        AND a.detail LIKE '%"alert_date": "' || m.alert_date || '"%') AS reason,
    EXISTS (SELECT 1 FROM mi_ep_alerts e WHERE e.ticker = m.ticker AND e.alert_date = m.alert_date) AS has_alert
  FROM mi_ep_catalyst_metrics m
  WHERE m.alert_date >= '2026-05-19' AND m.q_revenue_yoy_pct IS NOT NULL
), b AS (
  SELECT c.*, d.trade_date, d.open_price, d.close,
    row_number() OVER (PARTITION BY c.ticker, c.alert_date ORDER BY d.trade_date) - 1 AS k
  FROM c JOIN mi_daily_closes d ON d.ticker = c.ticker AND d.trade_date >= c.alert_date AND d.trade_date <= c.alert_date + 45
)
SELECT ticker, alert_date, era, coalesce(reason,'') AS reason, has_alert,
  max(open_price) FILTER (WHERE k = 0 AND trade_date = alert_date) AS o,
  max(close) FILTER (WHERE k = 5) AS c5,
  max(close) FILTER (WHERE k = 20) AS c20
FROM b GROUP BY 1,2,3,4,5 ORDER BY alert_date, ticker;
SELECT count(*) AS predicate_now FROM mi_ep_catalyst_metrics m
WHERE m.alert_date >= '2026-08-22' AND m.alert_date <= CURRENT_DATE - 12 AND m.q_revenue_yoy_pct IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM mi_audit_log a WHERE a.event_type = 'catalyst_earnings_revenue_weak_downgrade'
    AND a.detail LIKE '%"ticker": "' || m.ticker || '"%' AND a.detail LIKE '%"alert_date": "' || m.alert_date || '"%');
