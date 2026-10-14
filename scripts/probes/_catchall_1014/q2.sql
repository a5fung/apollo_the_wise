-- which live themes sit in the no-ecosystem catch-all on 10-14, how they got there (read-only)
WITH live AS (
  SELECT DISTINCT ON (name) name, theme_date, stage, tickers, created_at
    FROM mi_themes WHERE theme_date >= DATE '2026-10-07' ORDER BY name, theme_date DESC)
SELECT l.name, l.theme_date, l.stage, array_length(l.tickers,1) AS n,
       coalesce(e.e_code,'(no row)') AS e_code, e.method, e.assigned_at AT TIME ZONE 'America/New_York' AS assigned_et,
       l.created_at AT TIME ZONE 'America/New_York' AS theme_created_et
  FROM live l LEFT JOIN mi_theme_ecosystems e ON e.theme_name = l.name
 WHERE l.theme_date = (SELECT max(theme_date) FROM mi_themes)
   AND coalesce(e.e_code,'E-UNASSIGNED') = 'E-UNASSIGNED'
 ORDER BY l.name;
