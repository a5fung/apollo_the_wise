-- #333 measurement task (this session) — population read only, READ-ONLY, $0.
-- Distinct live-source EP-alert tickers, trailing 90 days.
SELECT DISTINCT ticker
FROM mi_ep_alerts
WHERE alert_date >= (CURRENT_DATE - INTERVAL '90 days')
  AND COALESCE(source, 'live') = 'live'
ORDER BY ticker;
