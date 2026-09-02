\echo === CONF ===
SELECT id, ticker, alert_date, confidence_multiplier FROM mi_ep_alerts
WHERE COALESCE(source,'live')='live' ORDER BY id;
