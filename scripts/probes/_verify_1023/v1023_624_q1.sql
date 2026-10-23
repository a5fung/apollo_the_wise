\pset pager off
\pset format aligned
\echo === Q1-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === Q1-1 every heartbeat row ever (compact)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, detail::jsonb->>'date' d, detail::jsonb->>'verdict' v, detail::jsonb->>'screened' scr, detail::jsonb->>'cap_only_eligible' cap, detail::jsonb->>'reached_lane' reached, detail::jsonb->>'graded' graded, detail::jsonb->>'high' hi, detail::jsonb->>'ordered' ord, detail::jsonb->>'missing' miss, detail::jsonb->>'lane_enabled' en FROM mi_audit_log WHERE event_type='lowcap_paper_lane_heartbeat' ORDER BY id;
\echo === Q1-2 verdict tally
SELECT detail::jsonb->>'verdict' verdict, count(*) FROM mi_audit_log WHERE event_type='lowcap_paper_lane_heartbeat' GROUP BY 1;
\echo === Q1-3 lane error rows ever (any lowcap/paper_lane/smallcap error event)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,300) FROM mi_audit_log WHERE event_type ILIKE '%lowcap%error%' OR event_type ILIKE '%paper_lane%error%' OR event_type ILIKE '%smallcap%error%' ORDER BY id;
\echo === Q1-4 lowcap-ish event types since 10-10 (counts)
SELECT event_type, count(*), min(to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI')) first_et, max(to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI')) last_et FROM mi_audit_log WHERE created_at >= '2026-10-10 04:00+00' AND (event_type ILIKE '%lowcap%' OR event_type ILIKE '%smallcap%' OR event_type ILIKE '%paper_lane%') GROUP BY 1 ORDER BY 1;
\echo === Q1-5 lane tick rows per ET day: count, first, last, total errors (parsed from detail)
SELECT to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD') d, count(*) ticks, min(to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI')) first_et, max(to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI')) last_et, sum((detail::jsonb->>'errors')::int) errs, sum((detail::jsonb->>'graded')::int) graded_sum, max((detail::jsonb->>'candidates')::int) max_cands FROM mi_audit_log WHERE event_type='lowcap_paper_lane_tick' GROUP BY 1 ORDER BY 1;
\echo === Q1-6 lane table rows (all)
SELECT id, ticker, alert_date, strategy_id, to_char(first_graded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') fg, to_char(last_graded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') lg, score_tier, ep_score, reject_stage, left(reject_reason,60) rr, round(gap_pct::numeric,1) gap, round(market_cap/1e6) mcap_m, catalyst_quality, llm_catalyst_quality, judge_tier, lane_rule_version FROM mi_lowcap_paper_lane_alerts ORDER BY id;
\echo === Q1-7 mi_ep_alerts rows matching a lane ticker+date (must be 0)
SELECT a.id, a.ticker, a.alert_date, a.score_tier FROM mi_ep_alerts a JOIN mi_lowcap_paper_lane_alerts l ON l.ticker=a.ticker AND l.alert_date=a.alert_date;
\echo === Q1-8 mi_ep_alerts by date/tier since 10-05 (live-path baseline)
SELECT alert_date, score_tier, count(*) FROM mi_ep_alerts WHERE alert_date >= '2026-10-05' GROUP BY 1,2 ORDER BY 1,2;
\echo === Q1-9 trades: any smallcap/lowcap signal_type ever; trades since 10-12 by account/signal/status
SELECT account_mode, signal_type, status, count(*) FROM mi_live_trades WHERE signal_type ILIKE '%smallcap%' OR signal_type ILIKE '%lowcap%' GROUP BY 1,2,3;
SELECT account_mode, signal_type, status, count(*) FROM mi_live_trades WHERE created_at >= '2026-10-12 04:00+00' GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo === Q1-9b trades whose ticker is a lane ticker; newest 6 trades
SELECT t.id, t.ticker, t.signal_type, t.account_mode, t.status, t.alert_date, to_char(t.created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') c_et FROM mi_live_trades t WHERE t.ticker IN (SELECT ticker FROM mi_lowcap_paper_lane_alerts) OR t.id IN (SELECT id FROM mi_live_trades ORDER BY id DESC LIMIT 6) ORDER BY t.id DESC;
\echo === Q1-10 per-day: screened / cap-only names (heartbeat SQL verbatim) since 10-05
SELECT scan_date, COUNT(DISTINCT ticker) screened, COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) cap_only FROM mi_ep_scan_log WHERE scan_date >= '2026-10-05' GROUP BY 1 ORDER BY 1;
\echo === Q1-11 INDEPENDENT of the heartbeat classification: sub-500M, price>=5, gap>=5 names on the scan log since 10-19, any stage, one row per name-day
SELECT scan_date, ticker, round(min(market_cap)/1e6) mcap_m, round(max(prev_close)::numeric,2) pc, round(max(gap_pct)::numeric,1) max_gap, count(*) rows, string_agg(DISTINCT reject_stage,'/') stages, left(max(filter_reason),70) fr, min(to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI')) first_tick, max(to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI')) last_tick FROM mi_ep_scan_log WHERE scan_date >= '2026-10-19' AND market_cap IS NOT NULL AND market_cap < 500e6 AND prev_close >= 5 AND gap_pct >= 5 GROUP BY 1,2 ORDER BY 1,2;
\echo === Q1-12 ... and which of those name-days exist in the lane table
SELECT l.alert_date, l.ticker, l.reject_stage FROM mi_lowcap_paper_lane_alerts l WHERE l.alert_date >= '2026-10-19' ORDER BY 1,2;
\echo === Q1-13 scan log coverage per day since 10-12: rows, ticks, first/last created ET, rows after 18:15 ET
SELECT scan_date, count(*) nrows, count(DISTINCT scan_time_et) ticks, to_char(min(created_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') first_et, to_char(max(created_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') last_et FROM mi_ep_scan_log WHERE scan_date >= '2026-10-12' GROUP BY 1 ORDER BY 1;
\echo === Q1-14 mi_ep_scan_log mcap_too_small-stamped rows per day since 10-05 (is the stamp still being written?)
SELECT scan_date, count(*) FILTER (WHERE strpos(filter_reason, 'filter:mcap_too_small')>0) stamped_rows, count(DISTINCT ticker) FILTER (WHERE strpos(filter_reason, 'filter:mcap_too_small')>0) stamped_names, count(*) FILTER (WHERE market_cap IS NOT NULL AND market_cap < 500e6) subcap_rows, count(DISTINCT ticker) FILTER (WHERE market_cap IS NOT NULL AND market_cap < 500e6) subcap_names FROM mi_ep_scan_log WHERE scan_date >= '2026-10-05' GROUP BY 1 ORDER BY 1;
\echo === Q1-15 strategy row
SELECT strategy_id, phase, enabled, live_real_enabled, position_size_multiplier, max_concurrent_positions, profit_trigger_r, breakeven_arm_r, updated_at FROM mi_strategies WHERE strategy_id IN ('magna53_smallcap','magna53_lowcap','magna53');
\echo === Q1-16 job runs lowcap since 10-12 ET
SELECT id, job_id, to_char(started_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') st_et, round(duration_s::numeric,3) dur, status, left(error_message,120) err FROM mi_job_runs WHERE job_id ILIKE '%lowcap%' AND started_at >= '2026-10-12 04:00+00' ORDER BY id;
\echo === Q1-17 EP scan job durations inside ORB window (09:25-09:50 ET), this week vs baseline
SELECT job_id, to_char(started_at AT TIME ZONE 'America/New_York','YYYY-MM-DD') d, count(*) runs, round(avg(duration_s)::numeric,1) avg_s, round(max(duration_s)::numeric,1) max_s, count(*) FILTER (WHERE status<>'success') nonsuccess FROM mi_job_runs WHERE job_id ILIKE '%ep_scan%' AND started_at >= '2026-10-01 04:00+00' AND (started_at AT TIME ZONE 'America/New_York')::time BETWEEN '09:25' AND '09:50' GROUP BY 1,2 ORDER BY 2,1;
\echo === Q1-18 timeout / late-grade / lane-slot events since 10-12 (counts by type)
SELECT event_type, count(*), min(to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI')) f, max(to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI')) l FROM mi_audit_log WHERE created_at >= '2026-10-12 04:00+00' AND (event_type ILIKE '%timeout%' OR event_type ILIKE '%judge%' OR event_type ILIKE '%late%grade%') GROUP BY 1 ORDER BY 1;
\echo === Q1-19 safeguard rows lowcap
SELECT * FROM mi_safeguard_state WHERE safeguard ILIKE '%lowcap%' OR safeguard ILIKE '%smallcap%';
