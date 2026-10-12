\pset tuples_only on
\o themes_1012.tsv
SELECT name, stage, COALESCE(source,'live'), COALESCE(parent_theme,''), array_to_string(tickers,','), replace(replace(COALESCE(description,''),E'\t',' '),E'\n',' ') FROM mi_themes WHERE theme_date='2026-10-12' ORDER BY name;
\o eco.tsv
SELECT theme_name, e_code FROM mi_theme_ecosystems;
\o cooldowns.tsv
SELECT theme_a, theme_b, verdict, adjudicated_at::text FROM mi_theme_merge_cooldowns WHERE cooldown_until > '2026-10-12 21:10:48+00' AND adjudicated_at < '2026-10-12 21:10:48+00';
\o industries.tsv
SELECT ticker, industry FROM mi_ticker_overrides WHERE industry IS NOT NULL AND industry <> '';
\o ov_cols.tsv
SELECT column_name FROM information_schema.columns WHERE table_name='mi_ticker_overrides';
\o
