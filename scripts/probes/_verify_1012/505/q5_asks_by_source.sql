WITH a AS (
  SELECT id, (created_at AT TIME ZONE 'America/New_York')::date d, event_type,
         substring(detail from $$child='([^']*)'$$) child
  FROM mi_audit_log
  WHERE event_type IN ('theme_parent_pass_linked','theme_parent_pass_distinct','theme_parent_pass_inverted','theme_parent_pass_error')
    AND created_at > '2026-09-26'
), t AS (
  SELECT DISTINCT ON (name) name, source FROM mi_themes ORDER BY name, theme_date DESC
)
SELECT COALESCE(t.source,'(no row)') src, a.event_type, count(*) FROM a LEFT JOIN t ON t.name=a.child GROUP BY 1,2 ORDER BY 1,2;
