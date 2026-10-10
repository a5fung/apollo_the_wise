-- READ-ONLY exploration for the #486 weekly section. One run, output saved, never re-run.
-- (a) is (ticker, alert_date) unique in mi_ep_alerts?
SELECT 'a_uniq' AS q, count(*)::text AS n, count(DISTINCT (ticker, alert_date))::text AS n_distinct FROM mi_ep_alerts;
-- (b) fire_axes shape over the last 120 days
SELECT 'b_fire_axes' AS q,
       CASE WHEN fire_axes IS NULL THEN 'null'
            WHEN cardinality(fire_axes) = 0 THEN 'empty'
            WHEN 'theme' = ANY(fire_axes) THEN 'has_theme'
            ELSE 'other_axes' END AS shape,
       count(*)::text, min(alert_date)::text, max(alert_date)::text
  FROM mi_ep_alerts WHERE alert_date >= CURRENT_DATE - 120 GROUP BY 2 ORDER BY 2;
-- (c) in_active_theme null-ness
SELECT 'c_in_active' AS q, in_active_theme::text, count(*)::text
  FROM mi_ep_alerts WHERE alert_date >= CURRENT_DATE - 120 GROUP BY 2 ORDER BY 2;
-- (d) shadow live_scan x alerts join: how many shadow live_scan rows find an alert row, by fire_axes shape
SELECT 'd_join' AS q, s.source, s.bounded_matches_unbounded::text AS bmu,
       CASE WHEN a.ticker IS NULL THEN 'no_alert'
            WHEN a.fire_axes IS NULL THEN 'fa_null'
            WHEN cardinality(a.fire_axes) = 0 THEN 'fa_empty'
            ELSE 'fa_present' END AS shape,
       count(*)::text
  FROM mi_theme_axis_shadow s
  LEFT JOIN mi_ep_alerts a ON a.ticker = s.ticker AND a.alert_date = s.alert_date
 WHERE s.alert_date >= CURRENT_DATE - 120
 GROUP BY 2, 3, 4 ORDER BY 2, 3, 4;
-- (e) stage vocabulary in the shadow (unbounded and bounded)
SELECT 'e_stage' AS q, coalesce(theme_stage, '<null>') AS st, coalesce(theme_stage_7d, '<null>') AS st7, count(*)::text
  FROM mi_theme_axis_shadow WHERE source = 'live_scan' AND bounded_matches_unbounded GROUP BY 2, 3 ORDER BY 4 DESC;
-- (f) weekly rate of the clean cohort: live_scan, bounded=true, joined to an alert with fire_axes, per ISO week
SELECT 'f_weekly' AS q, date_trunc('week', s.alert_date)::date::text AS wk, count(*)::text AS n
  FROM mi_theme_axis_shadow s
  JOIN mi_ep_alerts a ON a.ticker = s.ticker AND a.alert_date = s.alert_date
 WHERE s.source = 'live_scan' AND s.bounded_matches_unbounded IS TRUE
   AND a.fire_axes IS NOT NULL AND s.alert_date >= CURRENT_DATE - 70
 GROUP BY 2 ORDER BY 2;
