-- READ-ONLY. What are the duplicate (ticker, alert_date) rows in mi_ep_alerts, and do they disagree
-- on the two fields the #486 section reads (in_active_theme, fire_axes)?
SELECT a.id, a.ticker, a.alert_date::text, a.source, a.score_tier, a.in_active_theme::text AS iat,
       coalesce(array_to_string(a.fire_axes, ','), '<null>') AS fa,
       a.detected_at::text, a.created_at::text, a.grade_engine_authority
  FROM mi_ep_alerts a
 WHERE (a.ticker, a.alert_date) IN (
        SELECT ticker, alert_date FROM mi_ep_alerts GROUP BY 1, 2 HAVING count(*) > 1)
   AND a.alert_date >= CURRENT_DATE - 120
 ORDER BY a.alert_date DESC, a.ticker, a.id
 LIMIT 60;
SELECT 'dup_summary' AS q, count(*)::text AS groups,
       count(*) FILTER (WHERE n_iat > 1)::text AS differ_in_active_theme,
       count(*) FILTER (WHERE n_fa > 1)::text AS differ_fire_axes
  FROM (SELECT ticker, alert_date, count(DISTINCT in_active_theme) AS n_iat,
               count(DISTINCT fire_axes) AS n_fa
          FROM mi_ep_alerts GROUP BY 1, 2 HAVING count(*) > 1) d;
SELECT 'src' AS q, source, count(*)::text, min(alert_date)::text, max(alert_date)::text
  FROM mi_ep_alerts GROUP BY 2 ORDER BY 2;
