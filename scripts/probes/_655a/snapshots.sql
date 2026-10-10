-- #655(a) READ-ONLY: nightly snapshot rows for the three named churners (and their re-mint names),
-- to line up each cap row against what the theme looked like that night and the night before.
BEGIN TRANSACTION READ ONLY;
SELECT theme_date, stage, cardinality(tickers) AS n, array_to_string(tickers, ',') AS tickers, name
FROM mi_themes
WHERE theme_date >= '2026-09-21'
  AND (name ILIKE '%appalach%' OR name ILIKE '%offshore drilling%' OR name ILIKE '%natural gas distribution%')
ORDER BY name, theme_date;
COMMIT;
