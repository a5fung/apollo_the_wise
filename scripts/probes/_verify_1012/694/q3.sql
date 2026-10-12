\echo == Q9 Monday ticks with 2 pending names: their ranks (A-Z would put APUS before WFF)
SELECT to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') t, string_agg(ticker||'#'||rank_by_prescore, ' > ' ORDER BY rank_by_prescore) pending_in_rank_order, bool_or(in_active_theme) any_theme
FROM mi_ep_shortlist_shadow WHERE scan_date='2026-10-12' AND adv_source='pending' GROUP BY scan_time_et HAVING count(*)>=2 ORDER BY scan_time_et;
\echo == Q10 history: days where the board exceeded 20, and total scan days in the table
SELECT scan_date, max(board_n) max_board FROM mi_ep_shortlist_shadow GROUP BY 1 HAVING max(board_n)>20 ORDER BY 1;
SELECT count(DISTINCT scan_date) scan_days, min(scan_date) first_day FROM mi_ep_shortlist_shadow;
\echo == Q11 board_n distribution per day, last 15 scan days
SELECT scan_date, max(board_n) max_board FROM mi_ep_shortlist_shadow GROUP BY 1 ORDER BY 1 DESC LIMIT 15;
\echo == Q12 every Monday tick has >=1 rs_prev_complete row? ticks with zero
SELECT count(*) ticks_total, count(*) FILTER (WHERE pc=0) ticks_zero_prev_complete FROM (SELECT scan_time_et, count(*) FILTER (WHERE adv_source='rs_prev_complete') pc FROM mi_ep_shortlist_shadow WHERE scan_date='2026-10-12' GROUP BY 1) x;
\echo == Q13 Monday audit rows
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') ts, event_type, left(coalesce(detail::text,''),160) d FROM mi_audit_log WHERE created_at > now() - interval '30 hours' AND (event_type ILIKE '%shortlist%' OR event_type ILIKE '%ep_scan%' OR event_type ILIKE '%lookup%') ORDER BY created_at DESC LIMIT 20;
