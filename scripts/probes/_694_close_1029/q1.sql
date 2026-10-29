SET default_transaction_read_only = on;
\echo == crowded days since the fix
SELECT scan_date, count(DISTINCT scan_time_et) AS ticks_over_20, max(board_n) AS max_board,
       min((scan_time_et AT TIME ZONE 'America/New_York')::time(0)) AS first_tick, max((scan_time_et AT TIME ZONE 'America/New_York')::time(0)) AS last_tick
FROM mi_ep_shortlist_shadow WHERE board_n > 20 AND scan_date >= DATE '2026-10-12' GROUP BY 1 ORDER BY 1;
\echo == every row of every crowded tick
SELECT scan_date, (scan_time_et AT TIME ZONE 'America/New_York')::time(0) AS t, minutes_since_open AS mso, board_n, acting_key,
       ticker, rank_by_prescore AS rk, shortlisted_by_prescore AS sl, adv_source, in_active_theme AS th, adv, prev_close, gap_pct
FROM mi_ep_shortlist_shadow WHERE board_n > 20 AND scan_date >= DATE '2026-10-12'
ORDER BY scan_date, scan_time_et, rank_by_prescore;
