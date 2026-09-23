-- #539 fixture data pull (read-only, capture-once). Split locally into per-table TSVs.
\pset format unaligned
\pset fieldsep '\t'
\pset null ''
\echo === BOARD ===
SELECT theme_date, name, source, stage, round(score::numeric,2) AS score,
       round(rs_avg::numeric,2) AS rs_avg, days_active, coalesce(parent_theme,'') AS parent_theme,
       array_to_string(tickers, ',') AS tickers
FROM mi_themes
WHERE theme_date BETWEEN DATE '2026-07-27' AND DATE '2026-08-06'
ORDER BY theme_date, name;
\echo === THESES ===
SELECT theme_date, name, stage,
       replace(replace(coalesce(description,''), E'\t', ' '), E'\n', ' ') AS description
FROM mi_themes
WHERE name IN ('Bitcoin Mining & Crypto Infrastructure Operators',
               'AI GPU Compute Infrastructure & Cloud Services',
               'AI Data Center Infrastructure Buildout')
  AND theme_date BETWEEN DATE '2026-08-03' AND DATE '2026-08-06'
ORDER BY name, theme_date;
\echo === RS ===
SELECT score_date, ticker, round(rs_composite::numeric,1) AS rs
FROM mi_stock_scores
WHERE ticker IN ('HUT','CIFR','BTDR','AMRC','BLZE','IREN','APLD','CRWV','WULF','CLSK','CORZ','SNOW')
  AND score_date BETWEEN DATE '2026-07-31' AND DATE '2026-08-06'
ORDER BY score_date, ticker;
\echo === LANE2 ===
SELECT run_date, source, name, array_to_string(tickers, ',') AS tickers
FROM mi_theme_candidates_shadow
WHERE source IN ('narrative_cogap','ecosystem_reactivation','narrative_seed')
  AND run_date BETWEEN DATE '2026-07-18' AND DATE '2026-08-06'
ORDER BY run_date, name;
