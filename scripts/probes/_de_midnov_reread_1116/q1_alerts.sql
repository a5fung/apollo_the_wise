SET default_transaction_read_only = on;
-- campaign population: live-source EP alerts from 2026-08-22, compact columns (no free text)
SELECT id, ticker, alert_date, gap_pct, ep_score, score_tier, catalyst_quality, COALESCE(source,'live') source,
       in_active_theme, fire_status, rubric_version, setup_class, (created_at AT TIME ZONE 'America/New_York') created_et
FROM mi_ep_alerts WHERE alert_date >= DATE '2026-08-22' ORDER BY alert_date, ticker, created_at;
