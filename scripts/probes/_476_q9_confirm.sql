\echo '--- NRIX in mi_themes EVER (no date limit) ---'
SELECT theme_date, name, stage FROM mi_themes WHERE 'NRIX' = ANY(tickers) ORDER BY theme_date DESC LIMIT 10;
\echo '--- Did "Next-Gen Oncology Platform Re-Rating" ever persist? ---'
SELECT theme_date, name, stage, array_length(tickers,1) n, source FROM mi_themes WHERE name ILIKE 'Next-Gen Oncology%' ORDER BY theme_date;
\echo '--- Current (last 2 days) active theme count + biotech-family share ---'
SELECT
  COUNT(*) FILTER (WHERE stage != 'Retired') AS active_themes,
  COUNT(*) FILTER (WHERE stage != 'Retired' AND name ~* 'oncolog|autoimmun|inflammat|rare|orphan|biotech|clinical|therapeut|pharma|genom|biopsy|peptide|degradation|antibody|immunolog|gene ') AS biotech_family_active
FROM (SELECT DISTINCT ON (name) name, stage FROM mi_themes WHERE theme_date >= CURRENT_DATE - 2 ORDER BY name, theme_date DESC) x;
