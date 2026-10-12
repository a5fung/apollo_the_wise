\echo == Q1 now / latest complete score date
SELECT now() AT TIME ZONE 'America/New_York' AS now_et;
SELECT score_date, count(*) n, count(adv_20) n_adv FROM mi_stock_scores GROUP BY 1 ORDER BY 1 DESC LIMIT 6;
\echo == Q2 shadow per day adv_source counts (last 6 scan dates)
SELECT scan_date, adv_source, count(*) rows, count(DISTINCT scan_time_et) ticks, max(board_n) max_board, min(scan_time_et AT TIME ZONE 'America/New_York') first_tick, max(scan_time_et AT TIME ZONE 'America/New_York') last_tick
FROM mi_ep_shortlist_shadow WHERE scan_date >= '2026-10-05' GROUP BY 1,2 ORDER BY 1 DESC, 2;
\echo == Q3 Monday ticks
SELECT to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS') t, count(*) rows, max(board_n) board_n, count(*) FILTER (WHERE adv_source='rs_prev_complete') prev_complete, count(*) FILTER (WHERE adv_source='pending') pending, count(*) FILTER (WHERE adv_source NOT IN ('rs_prev_complete','pending') OR adv_source IS NULL) other, count(*) FILTER (WHERE shortlisted_by_prescore) shortlisted, acting_key
FROM mi_ep_shortlist_shadow WHERE scan_date='2026-10-12' GROUP BY scan_time_et, acting_key ORDER BY scan_time_et;
