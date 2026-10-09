-- #694 per day, per pre-open tick: rows, rows with rank_by_gap, max rank_by_gap (board size), distinct tickers
SELECT scan_date,
       to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS.US') AS t_et,
       count(*) n_rows,
       count(rank_by_gap) n_rank_gap,
       max(rank_by_gap) max_rank_gap,
       count(DISTINCT ticker) n_tickers,
       count(rank_by_prescore) n_rank_pre,
       count(*) FILTER (WHERE rank_by_gap IS NULL) n_no_rank
  FROM mi_ep_scan_log
 WHERE scan_date BETWEEN '2026-04-13' AND '2026-10-08'
   AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '10:00'
 GROUP BY 1,2 ORDER BY 1,2;
