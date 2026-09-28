-- #684 CRITIC — were the "strictly prior" snapshots actually WRITTEN before the gap day? Read-only, $0.
-- For every population pair: the theme row the study joins (hottest non-Retired snapshot containing the
-- ticker, theme_date <= scan_date - 1) and when that row was created; the rank-shadow row and when it was
-- computed.  A row created after the scan date is a backfill whose contents could carry later knowledge.
\pset format unaligned
\pset fieldsep '|'
\pset footer off
WITH t AS (
  SELECT ticker, scan_date FROM mi_ep_scan_log
  WHERE scan_date BETWEEN DATE '2026-05-01' AND DATE '2026-09-03' AND ep_score IS NOT NULL
  GROUP BY 1, 2
), th AS (
  SELECT t.ticker, t.scan_date, u.theme_date, u.name, (u.created_at AT TIME ZONE 'America/New_York')::date AS created_d, u.source
  FROM t LEFT JOIN LATERAL (
    SELECT * FROM mi_themes m WHERE t.ticker = ANY(m.tickers) AND m.stage <> 'Retired' AND m.theme_date <= t.scan_date - 1
    ORDER BY m.theme_date DESC, m.score DESC NULLS LAST LIMIT 1) u ON TRUE
), rs AS (
  SELECT t.ticker, t.scan_date, (r.computed_at AT TIME ZONE 'America/New_York')::date AS computed_d
  FROM t JOIN LATERAL (SELECT * FROM mi_alert_rank_shadow r WHERE r.ticker = t.ticker AND r.alert_date = t.scan_date ORDER BY r.computed_at DESC LIMIT 1) r ON TRUE
)
SELECT 'theme_joined', count(*)::text FROM th WHERE theme_date IS NOT NULL
UNION ALL SELECT 'theme_row_created_on_or_before_scan_date', count(*)::text FROM th WHERE theme_date IS NOT NULL AND created_d <= scan_date
UNION ALL SELECT 'theme_row_created_after_scan_date', count(*)::text FROM th WHERE theme_date IS NOT NULL AND created_d > scan_date
UNION ALL SELECT 'theme_row_created_after_scan_date_lag_' || CASE WHEN created_d - scan_date <= 7 THEN '1-7d' WHEN created_d - scan_date <= 30 THEN '8-30d' ELSE '>30d' END, count(*)::text FROM th WHERE theme_date IS NOT NULL AND created_d > scan_date GROUP BY 1
UNION ALL SELECT 'theme_joined_source_' || COALESCE(source, 'NULL'), count(*)::text FROM th WHERE theme_date IS NOT NULL GROUP BY source
UNION ALL SELECT 'mi_themes_rows_0425_0902_by_created_lag_' || CASE WHEN (created_at AT TIME ZONE 'America/New_York')::date - theme_date <= 1 THEN '0-1d' WHEN (created_at AT TIME ZONE 'America/New_York')::date - theme_date <= 7 THEN '2-7d' ELSE '>7d' END, count(*)::text FROM mi_themes WHERE theme_date BETWEEN DATE '2026-04-25' AND DATE '2026-09-02' GROUP BY 1
UNION ALL SELECT 'rank_shadow_rows', count(*)::text FROM rs
UNION ALL SELECT 'rank_shadow_computed_same_day', count(*)::text FROM rs WHERE computed_d = scan_date
UNION ALL SELECT 'rank_shadow_computed_later_' || CASE WHEN computed_d - scan_date <= 7 THEN '1-7d' WHEN computed_d - scan_date <= 30 THEN '8-30d' ELSE '>30d' END, count(*)::text FROM rs WHERE computed_d > scan_date GROUP BY 1
;
