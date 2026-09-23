\pset format unaligned
\pset fieldsep '\t'
\pset footer off
SELECT ticker, alert_date, score_tier, ep_score, gap_pct, in_active_theme, source, (detected_at AT TIME ZONE 'America/New_York')::date AS detected_et FROM mi_ep_alerts ORDER BY alert_date, ticker;
