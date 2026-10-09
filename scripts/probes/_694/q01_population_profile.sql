-- #694 population profile: which scan-log rows reached the shortlist sort, by pre-open vs open
SELECT ((scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30') AS pre_open,
       reject_stage,
       left(regexp_replace(coalesce(filter_reason,'<null>'),'[0-9][0-9.,%$x]*','#','g'),45) AS reason_shape,
       (rank_by_gap IS NOT NULL) AS has_rank_gap,
       (rank_by_prescore IS NOT NULL) AS has_rank_prescore,
       count(*) n, min(scan_date) first_d, max(scan_date) last_d
  FROM mi_ep_scan_log
 WHERE scan_date BETWEEN '2026-04-13' AND '2026-10-08'
 GROUP BY 1,2,3,4,5 ORDER BY 1,6 DESC;
