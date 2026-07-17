WITH latest AS (SELECT MAX(score_date) d FROM mi_stock_scores),
elite AS (
  SELECT ticker, rs_composite, sector
  FROM mi_stock_scores, latest
  WHERE score_date = latest.d
    AND ticker IN ('NRIX','AGIO','ZBIO','ELVN','TGTX','RARE','XENE','ANNX','ACAD','KURA','DNTH','ALMS')
),
active_themes AS (
  SELECT DISTINCT ON (name) name, tickers, stage
  FROM mi_themes
  WHERE theme_date >= CURRENT_DATE - 7 AND stage != 'Retired'
  ORDER BY name, theme_date DESC
)
SELECT e.ticker, e.rs_composite, e.sector,
       COALESCE((SELECT string_agg(a.name, ' | ') FROM active_themes a WHERE e.ticker = ANY(a.tickers)), '(NONE-ORPHAN)') AS in_themes
FROM elite e ORDER BY e.rs_composite DESC;
