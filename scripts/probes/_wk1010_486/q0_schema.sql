-- READ-ONLY. Schema of the two tables the #486 section joins.
SELECT 'shadow' AS t, column_name, data_type FROM information_schema.columns
 WHERE table_name = 'mi_theme_axis_shadow' ORDER BY ordinal_position;
SELECT 'alerts' AS t, column_name, data_type FROM information_schema.columns
 WHERE table_name = 'mi_ep_alerts' AND column_name IN
 ('ticker','alert_date','in_active_theme','fire_axes','score_tier','judge_tier','grade_engine_authority','scan_date','created_at')
 ORDER BY ordinal_position;
SELECT 'shadow_source' AS t, source, count(*)::text, min(alert_date)::text, max(alert_date)::text
  FROM mi_theme_axis_shadow GROUP BY source;
SELECT 'bounded' AS t, bounded_matches_unbounded::text, count(*)::text FROM mi_theme_axis_shadow GROUP BY 2;
