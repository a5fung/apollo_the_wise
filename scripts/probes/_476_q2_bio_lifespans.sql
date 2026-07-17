WITH bio AS (
  SELECT name, theme_date, stage, source, array_length(tickers,1) AS n,
         parent_theme
  FROM mi_themes
  WHERE theme_date >= CURRENT_DATE - 35
    AND ( name ~* 'oncolog|cancer|tumor|autoimmun|inflammat|immunolog|gene (therapy|edit)|cell therapy|genom|crispr|mrna|biotech|clinical|therapeut|pharma|orphan|rare (disease|neuro|metabol)|biopsy|neuro|metabol|cns|cardiometab|ophthalm' )
)
SELECT name,
       MIN(theme_date) AS first_seen,
       MAX(theme_date) AS last_seen,
       COUNT(DISTINCT theme_date) AS days_seen,
       MAX(n) AS max_members,
       (array_agg(stage ORDER BY theme_date DESC))[1] AS last_stage,
       (array_agg(source ORDER BY theme_date DESC))[1] AS last_source
FROM bio
GROUP BY name
ORDER BY last_seen DESC, days_seen DESC;
