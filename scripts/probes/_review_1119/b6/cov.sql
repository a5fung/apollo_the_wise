SET default_transaction_read_only = on;
WITH c AS (
 SELECT m.ticker, m.alert_date,
  CASE WHEN EXISTS (SELECT 1 FROM mi_audit_log a WHERE a.event_type='catalyst_earnings_revenue_weak_downgrade'
      AND a.detail LIKE '%"ticker": "'||m.ticker||'"%' AND a.detail LIKE '%"alert_date": "'||m.alert_date||'"%') THEN 'DOWN' ELSE 'PASS' END v
 FROM mi_ep_catalyst_metrics m WHERE m.alert_date >= '2026-08-22' AND m.q_revenue_yoy_pct IS NOT NULL)
SELECT v, count(*) n,
 count(*) FILTER (WHERE EXISTS (SELECT 1 FROM mi_intraday_bars b WHERE b.ticker=c.ticker AND (b.bar_time AT TIME ZONE 'America/New_York')::date=c.alert_date)) with_bars
FROM c GROUP BY v;
