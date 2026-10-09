-- #694 rows per mi_stock_scores score_date (input to the latest-complete-date rule, replicated locally)
SELECT score_date, count(*) n, count(adv_20) n_adv, count(rs_rank) n_rank FROM mi_stock_scores
 WHERE score_date BETWEEN '2026-02-01' AND '2026-10-08' GROUP BY 1 ORDER BY 1;
