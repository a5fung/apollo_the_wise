SET default_transaction_read_only = on;
SELECT count(*) FROM "mi_lowcap_lane_signals" WHERE EXISTS (SELECT 1 FROM mi_ep_alerts e WHERE e.ticker = mi_lowcap_lane_signals.ticker AND e.alert_date < mi_lowcap_lane_signals.scan_date AND e.alert_date >= mi_lowcap_lane_signals.scan_date - 60 AND COALESCE(e.source, 'live') = 'live');
