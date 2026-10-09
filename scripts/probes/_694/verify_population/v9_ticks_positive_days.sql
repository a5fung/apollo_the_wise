-- verify #694: every pre-open tick's ranked board on the 4 crowded days holding a real EP (05-06, 05-07, 08-04, 08-07),
-- to test baseline A (today's live order) at EVERY pre-open tick, not only the last. Read-only.
SELECT scan_date, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS.US') tick, ticker, rank_by_gap, left(coalesce(filter_reason,''),40) fr
  FROM mi_ep_scan_log
 WHERE scan_date IN ('2026-05-06','2026-05-07','2026-08-04','2026-08-07') AND rank_by_gap IS NOT NULL
   AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30'
 ORDER BY 1,2,4;
