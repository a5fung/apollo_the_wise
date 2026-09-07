\pset format unaligned
\pset fieldsep '\t'
\pset footer off
SELECT id, ticker, alert_date, grade, theme_name, theme_stage, themeless_flag, theme_name_7d, theme_stage_7d, bounded_matches_unbounded, (created_at AT TIME ZONE 'America/New_York')::date AS created_et, ((created_at AT TIME ZONE 'America/New_York')::date = alert_date) AS same_day_write FROM mi_theme_axis_shadow ORDER BY alert_date, ticker;
