\echo == Q4 Monday rows joined to last night's score row (10-09)
SELECT to_char(s.scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') t, s.rank_by_prescore rk, s.ticker, s.gap_pct, s.prev_close, s.adv, s.adv_source, s.in_active_theme theme, s.board_n, m.adv_20 AS m_adv_1009, (m.adv_20 IS NULL) AS no_m_adv, (m.ticker IS NULL) AS no_m_row, (s.adv = m.adv_20) AS adv_matches
FROM mi_ep_shortlist_shadow s LEFT JOIN mi_stock_scores m ON m.ticker=s.ticker AND m.score_date='2026-10-09'
WHERE s.scan_date='2026-10-12' AND s.scan_time_et IN (SELECT scan_time_et FROM mi_ep_shortlist_shadow WHERE scan_date='2026-10-12' AND to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') IN ('07:05','09:15','09:25','09:35','09:55'))
ORDER BY s.scan_time_et, s.rank_by_prescore;
\echo == Q5 summary over ALL Monday rows: adv_source vs whether mi_stock_scores had a usable adv_20 on 10-09
SELECT s.adv_source, (m.adv_20 IS NOT NULL) AS had_prev_adv, count(*) n, count(DISTINCT s.ticker) tickers
FROM mi_ep_shortlist_shadow s LEFT JOIN mi_stock_scores m ON m.ticker=s.ticker AND m.score_date='2026-10-09'
WHERE s.scan_date='2026-10-12' GROUP BY 1,2 ORDER BY 1,2;
\echo == Q6 Monday ticker list
SELECT ticker, adv_source, count(*) n, min(gap_pct) mn_gap, max(gap_pct) mx_gap FROM mi_ep_shortlist_shadow WHERE scan_date='2026-10-12' GROUP BY 1,2 ORDER BY 1;
\echo == Q7 friday ticks with >=2 pending names: were pending order A-Z? (baseline)
SELECT scan_date, count(DISTINCT scan_time_et) ticks_with_pending_ge2 FROM (SELECT scan_date, scan_time_et FROM mi_ep_shortlist_shadow WHERE adv_source='pending' AND scan_date>='2026-10-05' GROUP BY 1,2 HAVING count(*)>=2) x GROUP BY 1 ORDER BY 1;
\echo == Q8 audit events last 24h mentioning shortlist/ep scan errors
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') ts, event_type, left(coalesce(details::text,''),200) d FROM mi_audit_log WHERE created_at > now() - interval '30 hours' AND (event_type ILIKE '%shortlist%' OR event_type ILIKE '%ep_scan%' OR event_type ILIKE '%last_night%' OR event_type ILIKE '%adv%') ORDER BY created_at DESC LIMIT 30;
