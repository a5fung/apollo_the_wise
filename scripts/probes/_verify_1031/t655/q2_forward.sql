SET default_transaction_read_only = on;
\echo == forward: themes after each suppression sharing >= half of the cohort (intersection over the smaller), other than the join target
WITH c AS (
  SELECT id, name, first_seen, join_target, tickers FROM mi_theme_birth_candidates
  WHERE last_outcome = 'join' AND join_target IS NOT NULL AND join_target <> name AND sightings = 1 AND first_seen >= '2026-09-14'
), m AS (
  SELECT c.id AS cand, t.name AS theme, t.theme_date,
         cardinality(ARRAY(SELECT unnest(c.tickers) INTERSECT SELECT unnest(t.tickers)))::float
           / NULLIF(LEAST(cardinality(c.tickers), cardinality(t.tickers)), 0) AS ov
  FROM c JOIN mi_themes t ON t.theme_date > c.first_seen
)
SELECT cand, theme, count(DISTINCT theme_date) AS days, min(theme_date) AS first_day, max(theme_date) AS last_day, round(max(ov)::numeric,2) AS max_ov
FROM m WHERE ov >= 0.5 GROUP BY cand, theme ORDER BY cand, days DESC;
\echo == the join targets: are they live themes, and since when
SELECT name, count(DISTINCT theme_date) AS days, min(theme_date), max(theme_date) FROM mi_themes
WHERE name IN (SELECT join_target FROM mi_theme_birth_candidates WHERE last_outcome='join' AND join_target IS NOT NULL AND join_target<>name AND sightings=1 AND first_seen>='2026-09-14')
GROUP BY name ORDER BY 1;
\echo == latest theme_date in the table
SELECT max(theme_date) FROM mi_themes;
