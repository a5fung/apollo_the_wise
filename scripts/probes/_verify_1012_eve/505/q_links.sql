\echo == mi_theme_ecosystems columns
SELECT column_name FROM information_schema.columns WHERE table_name='mi_theme_ecosystems' ORDER BY ordinal_position;
\echo == parent links on 10-09 (non-Retired)
SELECT name, stage, parent_theme FROM mi_themes WHERE theme_date='2026-10-09' AND parent_theme IS NOT NULL AND stage<>'Retired' ORDER BY name;
\echo == parent links on 10-12 (non-Retired)
SELECT name, stage, parent_theme FROM mi_themes WHERE theme_date='2026-10-12' AND parent_theme IS NOT NULL AND stage<>'Retired' ORDER BY name;
\echo == 10-12 retired rows with a parent pointer, count and whether the 10-09 row was one of the 9 links
SELECT count(*) FROM mi_themes WHERE theme_date='2026-10-12' AND stage='Retired';
SELECT count(*) FROM mi_themes WHERE theme_date='2026-10-12' AND stage='Retired' AND parent_theme IS NOT NULL;
