SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_date, event_type, detail
FROM mi_audit_log
WHERE created_at >= NOW() - INTERVAL '30 days'
  AND event_type IN ('theme_cap_drop','theme_cap_strip')
ORDER BY created_at DESC LIMIT 25;
