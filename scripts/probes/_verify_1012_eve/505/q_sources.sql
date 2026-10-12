WITH a AS (
  SELECT id, (created_at AT TIME ZONE 'America/New_York')::date d, event_type,
         substring(detail from $$child='([^']*)'$$) child, substring(detail from $$parent='([^']*)'$$) parent
  FROM mi_audit_log
  WHERE event_type IN ('theme_parent_pass_linked','theme_parent_pass_distinct','theme_parent_pass_inverted','theme_parent_pass_error')
    AND created_at > '2026-09-26'
)
SELECT a.d, a.event_type, left(a.child,60) child, COALESCE(t.source,'(no row that day)') src_on_day
FROM a LEFT JOIN mi_themes t ON t.name=a.child AND t.theme_date=a.d
WHERE COALESCE(t.source,'x') <> 'live' OR a.event_type='theme_parent_pass_linked'
ORDER BY a.id;
\echo == counts by source on the day of the ask
WITH a AS (
  SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, substring(detail from $$child='([^']*)'$$) child
  FROM mi_audit_log WHERE event_type LIKE 'theme_parent_pass_%' AND event_type <> 'theme_parent_pass_ran' AND created_at > '2026-09-26')
SELECT COALESCE(t.source,'(no row that day)') src, count(*) FROM a LEFT JOIN mi_themes t ON t.name=a.child AND t.theme_date=a.d GROUP BY 1 ORDER BY 1;
