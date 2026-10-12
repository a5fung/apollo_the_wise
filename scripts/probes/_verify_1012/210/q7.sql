\echo === V1 audit row full
SELECT * FROM mi_audit_log WHERE event_type='tv_news_shadow_run' AND created_at >= '2026-10-12' ORDER BY created_at;
\echo === V2 HUM row full
SELECT * FROM mi_tv_news_shadow WHERE ticker='HUM' AND alert_date='2026-10-09';
\echo === V3 any tradingview endpoint anomaly / shadow error events today
SELECT event_type, created_at AT TIME ZONE 'America/New_York' AS at_et, left(coalesce(summary,''),200) FROM mi_audit_log WHERE created_at >= '2026-10-12' AND (event_type ILIKE '%tv_%' OR event_type ILIKE '%tradingview%' OR event_type ILIKE '%endpoint_shape%' OR event_type ILIKE '%grade_corpus%');
