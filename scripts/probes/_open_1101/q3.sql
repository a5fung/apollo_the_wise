SET default_transaction_read_only = on;
SELECT MAX(alert_date) AS shadow_max, COUNT(DISTINCT alert_date) FILTER (WHERE alert_date > '2026-08-16') AS oos_sessions FROM mi_alert_rank_shadow;
SELECT MAX(alert_date) AS alerts_max FROM mi_ep_alerts;
