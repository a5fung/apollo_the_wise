SELECT min(alert_date) AS min_d, max(alert_date) AS max_d, count(DISTINCT ticker) AS n_tickers, count(*) AS n_alerts
FROM mi_ep_alerts
WHERE alert_date >= (CURRENT_DATE - INTERVAL '90 days')
  AND COALESCE(source, 'live') = 'live';
