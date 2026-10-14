-- theme-hierarchy health 10-14: the catch-all growth he pasted (read-only)
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, left(detail::text, 1500) AS detail
  FROM mi_audit_log WHERE event_type = 'theme_hierarchy_health'
 ORDER BY id DESC LIMIT 3;
