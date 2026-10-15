\pset pager off
\echo === Q3-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === Q3-1 BETR lane row vs DFH live scan row at 09:55: same 33.8 score, are the breakdowns the same object or different inputs
SELECT 'lane BETR' src, ep_score, jsonb_pretty(score_breakdown) bd FROM mi_lowcap_paper_lane_alerts WHERE ticker='BETR' AND alert_date='2026-10-15';
SELECT 'live DFH 09:55' src, ep_score, jsonb_pretty(score_breakdown) bd FROM mi_ep_scan_log WHERE ticker='DFH' AND scan_date='2026-10-15' AND ep_score IS NOT NULL ORDER BY id DESC LIMIT 1;
\echo === Q3-1b the inputs of each: gap, rel_volume, pm_rvol, price, atr, adv, theme, catalyst for BETR lane row and DFH live row
SELECT 'lane BETR' src, round(gap_pct::numeric,2) gap, round(rel_volume::numeric,2) rv, round(pm_rvol::numeric,2) pmrv, round(current_price::numeric,2) px, round(atr_pct::numeric,1) atr, round(quality_adv_dollar/1e6,1) adv_m, in_active_theme, catalyst_quality FROM mi_lowcap_paper_lane_alerts WHERE ticker='BETR' AND alert_date='2026-10-15'
UNION ALL
SELECT 'live DFH', round(gap_pct::numeric,2), round(rel_volume::numeric,2), round(pm_rvol::numeric,2), round(current_price::numeric,2), round(atr_pct::numeric,1), round(quality_adv_dollar/1e6,1), in_active_theme, catalyst_quality FROM mi_ep_scan_log WHERE ticker='DFH' AND scan_date='2026-10-15' AND ep_score IS NOT NULL ORDER BY 1 DESC LIMIT 5;
\echo === Q3-2 provenance rows (grader ran) for the two lane names, full detail
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t_et, event_type, summary, left(detail,400) d FROM mi_audit_log WHERE created_at >= '2026-10-15 04:00+00' AND event_type='ep_catalyst_provenance' AND (summary LIKE 'OPI %' OR summary LIKE 'BETR %') ORDER BY id;
\echo === Q3-3 per-tick join: every live scan tick that logged a cap-only name vs a lane tick audit row within 150s after it (any miss = a dropped tick)
WITH s AS (SELECT DISTINCT scan_time_et AS t FROM mi_ep_scan_log WHERE scan_date='2026-10-15' AND reject_stage='quality_filter' AND strpos(filter_reason,'filter:mcap_too_small')>0),
     l AS (SELECT created_at AS t FROM mi_audit_log WHERE event_type='lowcap_paper_lane_tick' AND created_at >= '2026-10-15 04:00+00' AND created_at < '2026-10-16 04:00+00')
SELECT count(*) scan_ticks_with_cap_only, count(*) FILTER (WHERE EXISTS (SELECT 1 FROM l WHERE l.t >= s.t - interval '5 seconds' AND l.t <= s.t + interval '150 seconds')) matched_to_lane_tick, (SELECT count(*) FROM l) lane_ticks_today FROM s;
SELECT to_char(s.t AT TIME ZONE 'America/New_York','HH24:MI:SS') unmatched_scan_tick FROM (SELECT DISTINCT scan_time_et AS t FROM mi_ep_scan_log WHERE scan_date='2026-10-15' AND reject_stage='quality_filter' AND strpos(filter_reason,'filter:mcap_too_small')>0) s WHERE NOT EXISTS (SELECT 1 FROM mi_audit_log a WHERE a.event_type='lowcap_paper_lane_tick' AND a.created_at >= s.t - interval '5 seconds' AND a.created_at <= s.t + interval '150 seconds');
\echo === Q3-4 order_status_reconcile_boot and other boot-only job runs around the 10-14 deploy
SELECT id, job_id, to_char(started_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') st_et, status FROM mi_job_runs WHERE job_id ILIKE '%boot%' AND started_at >= '2026-10-13 04:00+00' ORDER BY id;
\echo === Q3-5 api_failure_fmp rows by ET day, last 8 days (new burst or the standing pattern)
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD') d, count(*) n, min(to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI')) first_et, max(to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI')) last_et, count(DISTINCT left(summary,80)) distinct_msgs FROM mi_audit_log WHERE event_type='api_failure_fmp' AND created_at >= '2026-10-07 04:00+00' GROUP BY 1 ORDER BY 1;
\echo === Q3-6 heartbeat 10-15 written exactly once and after the scan finished
SELECT count(*) heartbeat_rows_1015, min(to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS')) at_et FROM mi_audit_log WHERE event_type='lowcap_paper_lane_heartbeat' AND summary LIKE '2026-10-15%';
\echo === Q3-7 paper account activity: any non-live trade rows or lane order ids since go-live, and any live-book row carrying the lane strategy id
SELECT account_mode, signal_type, count(*) FROM mi_live_trades WHERE signal_type ILIKE '%smallcap%' OR signal_type ILIKE '%lowcap%' OR (account_mode <> 'live' AND created_at >= '2026-10-10 04:00+00') GROUP BY 1,2;
SELECT strategy_id, phase, enabled, updated_at FROM mi_strategies WHERE strategy_id='magna53_smallcap';
