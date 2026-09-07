\pset format unaligned
\pset fieldsep '\t'
\pset footer off

SELECT score_date, ticker, rs_composite FROM mi_stock_scores WHERE score_date >= '2026-03-01' AND ticker IN (SELECT DISTINCT unnest(tickers) FROM mi_themes) ORDER BY score_date, ticker;
