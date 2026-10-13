\echo === 1 live-path rows that reached grading inside 09:30-09:55 ET, 10-12 and 10-13 (stage past gap_floor/universe_floor)
SELECT scan_date, ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS') t_et, reject_stage, left(filter_reason,160) fr, round(gap_pct::numeric,1) gap, round(market_cap/1e6) mcap_m
FROM mi_ep_scan_log
WHERE scan_date IN ('2026-10-12','2026-10-13')
  AND (scan_time_et AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '09:55'
  AND reject_stage IN ('score_bar','post_grade_filter','quality_filter','extension','duplicate') OR (scan_date IN ('2026-10-12','2026-10-13') AND reject_stage IS NULL AND (scan_time_et AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '09:55')
ORDER BY scan_date, scan_time_et, ticker;
\echo === 2 does mi_ep_scan_log hold any row for a lane-only grade (ALLT/GOSS after their lane grade)
SELECT scan_date, ticker, count(*), array_agg(DISTINCT reject_stage) FROM mi_ep_scan_log WHERE scan_date IN ('2026-10-12','2026-10-13') AND ticker IN ('ALLT','GOSS') GROUP BY 1,2;
