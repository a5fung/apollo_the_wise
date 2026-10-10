-- #655 scope, READ-ONLY: columns + theme event-type counts over the last 21 days.
BEGIN TRANSACTION READ ONLY;
SELECT table_name, column_name, data_type FROM information_schema.columns
 WHERE table_name IN ('mi_themes','mi_theme_ecosystems','mi_theme_ecosystems_dynamic','mi_ticker_overrides','mi_daily_closes','mi_audit_log')
 ORDER BY table_name, ordinal_position;
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York')::date, max(created_at AT TIME ZONE 'America/New_York')::date
  FROM mi_audit_log WHERE created_at >= now() - interval '21 days' AND event_type LIKE 'theme%'
 GROUP BY 1 ORDER BY 2 DESC;
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, length(detail) FROM mi_audit_log WHERE event_type='theme_correctness_check' ORDER BY id;
COMMIT;
