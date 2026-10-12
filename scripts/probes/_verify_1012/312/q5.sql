SELECT alert_date, score_tier, COUNT(*) n FROM mi_ep_alerts WHERE alert_date >= DATE '2026-10-08' GROUP BY 1,2 ORDER BY 1,2;
SELECT ticker, score_tier, ep_score, theme_gated_tier, (detected_at AT TIME ZONE 'America/New_York') AS det_et FROM mi_ep_alerts WHERE alert_date = DATE '2026-10-12' ORDER BY detected_at;
