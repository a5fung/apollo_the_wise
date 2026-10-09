-- #694 mi_stock_scores for every ticker that appears in any pre-open pool or label pair (keys 1 and 4), 2026-04-20..2026-10-08
SELECT s.ticker, s.score_date, s.adv_20, s.rs_rank, s.rs_composite, s.close
  FROM mi_stock_scores s
 WHERE s.score_date BETWEEN '2026-04-20' AND '2026-10-08'
   AND s.ticker IN (SELECT DISTINCT ticker FROM mi_ep_scan_log
                     WHERE scan_date BETWEEN '2026-04-13' AND '2026-10-08' AND rank_by_gap IS NOT NULL
                       AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30')
 ORDER BY s.ticker, s.score_date;
