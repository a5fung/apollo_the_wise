\pset format unaligned
\pset fieldsep '\t'
\pset footer off
SELECT score_date, ticker, rs_composite, rs_rank, sector FROM mi_stock_scores WHERE score_date >= '2026-01-15' ORDER BY score_date, ticker;
