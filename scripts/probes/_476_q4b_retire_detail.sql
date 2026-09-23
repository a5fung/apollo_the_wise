SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_date, detail
FROM mi_audit_log
WHERE created_at >= NOW() - INTERVAL '30 days'
  AND event_type = 'theme_auto_retired'
ORDER BY created_at DESC;
