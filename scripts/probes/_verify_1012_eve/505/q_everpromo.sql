WITH a AS (
  SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type,
         substring(detail from $$child='([^']*)'$$) child
  FROM mi_audit_log WHERE event_type IN ('theme_parent_pass_linked','theme_parent_pass_distinct','theme_parent_pass_inverted') AND created_at > '2026-09-26')
SELECT a.d, a.event_type, left(a.child,70) child,
 (SELECT string_agg(DISTINCT t.source, ',') FROM mi_themes t WHERE t.name=a.child) sources_ever,
 (SELECT string_agg(t.theme_date::text||':'||t.source, ' ' ORDER BY t.theme_date) FROM mi_themes t WHERE t.name=a.child AND t.theme_date BETWEEN a.d-3 AND a.d+1) near
FROM a WHERE EXISTS (SELECT 1 FROM mi_themes t WHERE t.name=a.child AND t.source='shadow_promoted') ORDER BY a.d;
\echo == how the tonight-board shadow_promoted themes look (8)
SELECT name, stage, array_length(tickers,1) n, parent_theme, (SELECT min(theme_date) FROM mi_themes x WHERE x.name=t.name) first_seen
FROM mi_themes t WHERE theme_date='2026-10-12' AND source='shadow_promoted' AND stage<>'Retired' ORDER BY first_seen, name;
