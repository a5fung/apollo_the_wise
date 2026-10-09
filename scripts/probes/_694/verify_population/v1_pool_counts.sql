-- verify #694 (a): my own last-pre-open-tick board per day, independent of q03
\echo '### V1a per-day: last pre-open tick among ALL rows, and ranked-row count at that tick, and at the last tick that HAS ranked rows'
WITH pre AS (
  SELECT * FROM mi_ep_scan_log
   WHERE scan_date BETWEEN '2026-04-13' AND '2026-10-08'
     AND scan_time_et IS NOT NULL
     AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30'),
lt_all AS (SELECT scan_date, max(scan_time_et) t FROM pre GROUP BY 1),
lt_rank AS (SELECT scan_date, max(scan_time_et) t FROM pre WHERE rank_by_gap IS NOT NULL GROUP BY 1)
SELECT a.scan_date,
       to_char(a.t AT TIME ZONE 'America/New_York','HH24:MI:SS') last_any,
       to_char(r.t AT TIME ZONE 'America/New_York','HH24:MI:SS') last_ranked,
       (SELECT count(*) FROM pre p WHERE p.scan_date=a.scan_date AND p.scan_time_et=r.t AND p.rank_by_gap IS NOT NULL) n_ranked_at_last,
       (SELECT count(DISTINCT ticker) FROM pre p WHERE p.scan_date=a.scan_date AND p.scan_time_et=r.t AND p.rank_by_gap IS NOT NULL) n_tick_at_last,
       (SELECT max(rank_by_gap) FROM pre p WHERE p.scan_date=a.scan_date AND p.scan_time_et=r.t) max_rank_at_last,
       (SELECT count(*) FROM pre p WHERE p.scan_date=a.scan_date AND p.scan_time_et=r.t AND p.rank_by_gap IS NULL
          AND coalesce(p.reject_stage,'') NOT IN ('universe_floor','gap_floor')) n_unranked_not_floor_at_last
  FROM lt_all a LEFT JOIN lt_rank r USING (scan_date) ORDER BY 1;
\echo '### V1b ticker list at the last ranked pre-open tick for 2026-09-17, 2026-10-05, 2026-05-06, 2026-07-30, 2026-09-03, 2026-08-04'
WITH pre AS (
  SELECT * FROM mi_ep_scan_log
   WHERE scan_date IN ('2026-09-17','2026-10-05','2026-05-06','2026-07-30','2026-09-03','2026-08-04')
     AND rank_by_gap IS NOT NULL
     AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30'),
lt AS (SELECT scan_date, max(scan_time_et) t FROM pre GROUP BY 1)
SELECT p.scan_date, to_char(p.scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS') tick, p.ticker, p.rank_by_gap, p.rank_by_prescore, p.adv_source, p.in_active_theme
  FROM pre p JOIN lt ON lt.scan_date=p.scan_date AND lt.t=p.scan_time_et ORDER BY 1, p.rank_by_gap;
\echo '### V1c shortlist shadow: board_n and rows at the last pre-open tick per day (independent record of the sorted board, since 08-22)'
WITH s AS (SELECT * FROM mi_ep_shortlist_shadow
   WHERE (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30'),
lt AS (SELECT scan_date, max(scan_time_et) t FROM s GROUP BY 1)
SELECT s.scan_date, to_char(lt.t AT TIME ZONE 'America/New_York','HH24:MI:SS') tick, count(*) n_rows, max(board_n) board_n, min(board_n) board_n_min,
       string_agg(s.ticker, ',' ORDER BY s.ticker) tickers
  FROM s JOIN lt ON lt.scan_date=s.scan_date AND lt.t=s.scan_time_et GROUP BY 1,2 ORDER BY 1;
