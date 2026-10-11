-- #146 detection page: rows per score_date, to re-derive latest_complete_score_date_sql per scan date. SELECT-only.
SELECT score_date, COUNT(*) AS n FROM mi_stock_scores GROUP BY score_date ORDER BY score_date;
