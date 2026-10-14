\pset pager off
\echo === Q1-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === Q1-1 lane/heartbeat/replay audit rows since 10-13 18:00 ET (full)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS t_et, event_type, summary, detail FROM mi_audit_log WHERE created_at >= '2026-10-13 22:00+00' AND (event_type ILIKE '%lowcap%' OR event_type ILIKE '%paper_lane%' OR event_type ILIKE '%smallcap%') ORDER BY id;
\echo === Q1-1b every heartbeat row ever (full)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') t_et, summary, detail FROM mi_audit_log WHERE event_type='lowcap_paper_lane_heartbeat' ORDER BY id;
\echo === Q1-1c heartbeat verdict tally
SELECT detail::jsonb->>'verdict' verdict, count(*) FROM mi_audit_log WHERE event_type='lowcap_paper_lane_heartbeat' GROUP BY 1;
\echo === Q1-1d lane error rows ever (lowcap_paper_lane_error / lowcap_lane_error-ish)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,300) FROM mi_audit_log WHERE event_type ILIKE '%lowcap%error%' OR event_type ILIKE '%paper_lane%error%' OR event_type ILIKE '%smallcap%error%' ORDER BY id;
\echo === Q1-1e lowcap-ish event types since 10-10 00:00 ET (counts)
SELECT event_type, count(*), min(to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI')) first_et, max(to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI')) last_et FROM mi_audit_log WHERE created_at >= '2026-10-10 04:00+00' AND (event_type ILIKE '%lowcap%' OR event_type ILIKE '%smallcap%' OR event_type ILIKE '%paper_lane%') GROUP BY 1 ORDER BY 1;
\echo === Q1-1f lane tick rows (all days)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, summary FROM mi_audit_log WHERE event_type='lowcap_paper_lane_tick' ORDER BY id;
\echo === Q1-2 lane table rows (all)
SELECT id, ticker, alert_date, strategy_id, to_char(first_graded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') fg, to_char(last_graded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') lg, score_tier, ep_score, reject_stage, reject_reason, round(gap_pct::numeric,1) gap, round(market_cap/1e6) mcap_m, catalyst_quality, judge_tier, rubric_version, lane_rule_version FROM mi_lowcap_paper_lane_alerts ORDER BY id;
\echo === Q1-3 mi_ep_alerts rows matching a lane ticker+date (must be 0)
SELECT a.id, a.ticker, a.alert_date, a.score_tier FROM mi_ep_alerts a JOIN mi_lowcap_paper_lane_alerts l ON l.ticker=a.ticker AND l.alert_date=a.alert_date;
\echo === Q1-3b mi_ep_alerts by date/tier 10-05..today (live-path baseline)
SELECT alert_date, score_tier, count(*) FROM mi_ep_alerts WHERE alert_date >= '2026-10-05' GROUP BY 1,2 ORDER BY 1,2;
\echo === Q1-3c mi_ep_alerts: rows dated or created since 10-10
SELECT id, ticker, alert_date, score_tier, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') c_et FROM mi_ep_alerts WHERE alert_date >= '2026-10-10' OR created_at >= '2026-10-10 04:00+00' ORDER BY id;
\echo === Q1-4 trades: magna53_smallcap ever, by account
SELECT account_mode, signal_type, status, count(*) FROM mi_live_trades WHERE signal_type='magna53_smallcap' GROUP BY 1,2,3;
\echo === Q1-4b all trades created since 10-12 ET by account/signal/status
SELECT account_mode, signal_type, status, count(*) FROM mi_live_trades WHERE created_at >= '2026-10-12 04:00+00' GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo === Q1-4c trades whose ticker is a lane ticker, or newest 6 trades
SELECT t.id, t.ticker, t.signal_type, t.account_mode, t.status, t.alert_date, to_char(t.created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') c_et FROM mi_live_trades t WHERE t.ticker IN (SELECT ticker FROM mi_lowcap_paper_lane_alerts) OR t.id IN (SELECT id FROM mi_live_trades ORDER BY id DESC LIMIT 6) ORDER BY t.id DESC;
\echo === Q1-5 heartbeat screened/cap-only SQL verbatim, 10-14 and 10-13
SELECT '2026-10-14' d, COUNT(DISTINCT ticker) AS screened, COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) AS cap_only FROM mi_ep_scan_log WHERE scan_date = '2026-10-14'::date
UNION ALL
SELECT '2026-10-13', COUNT(DISTINCT ticker), COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) FROM mi_ep_scan_log WHERE scan_date = '2026-10-13'::date;
\echo === Q1-5b lane rows heartbeat SQL verbatim 10-14
SELECT ticker, score_tier, reject_stage FROM mi_lowcap_paper_lane_alerts WHERE alert_date = '2026-10-14'::date;
\echo === Q1-5c scan log 10-14: rows, ticks, first/last row ET, rows created after 18:15 ET
SELECT count(*) nrows, count(DISTINCT scan_time_et) ticks, to_char(min(created_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') first_et, to_char(max(created_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') last_et, count(*) FILTER (WHERE created_at >= '2026-10-14 22:15+00') after_hb FROM mi_ep_scan_log WHERE scan_date='2026-10-14';
\echo === Q1-5d sub-500M, $5+, gap>=9 names on scan log 10-14 with stage
SELECT ticker, reject_stage, left(filter_reason,100) fr, round(market_cap/1e6) mcap_m, round(gap_pct::numeric,1) gap, round(prev_close::numeric,2) pc, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') t_et FROM mi_ep_scan_log WHERE scan_date='2026-10-14' AND market_cap IS NOT NULL AND market_cap < 500e6 AND prev_close >= 5 AND gap_pct >= 9 ORDER BY ticker, id;
\echo === Q1-5e ALL mcap_too_small-stamped names 10-14 (any price/gap)
SELECT ticker, round(market_cap/1e6) mcap_m, count(*) rows, round(min(gap_pct)::numeric,1) min_gap, round(max(gap_pct)::numeric,1) max_gap, round(max(prev_close)::numeric,2) pc FROM mi_ep_scan_log WHERE scan_date='2026-10-14' AND strpos(filter_reason, 'filter:mcap_too_small') > 0 GROUP BY 1,2 ORDER BY 1;
\echo === Q1-6 paper lane replays (count + all rows, key cols)
SELECT count(*) FROM mi_lowcap_paper_lane_replays;
SELECT ticker, session_date, signal_id, to_char(tick_wallclock_et AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') tick_et, entry_status, entry_reason, outcome, final_reason, realized_r, admission_era, replay_exit_era, replay_exit_rules, replay_asof_date, settle_version, to_char(recorded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') rec_et, to_char(updated_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') upd_et FROM mi_lowcap_paper_lane_replays ORDER BY signal_id;
\echo === Q1-6b lowcap_lane_replay job runs since 10-09 ET
SELECT id, job_id, to_char(started_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') st_et, to_char(finished_at AT TIME ZONE 'America/New_York','HH24:MI:SS') fin_et, round(duration_s::numeric,3) dur, status, rows_written, left(error_message,160) err FROM mi_job_runs WHERE job_id ILIKE '%lowcap%' AND started_at >= '2026-10-09 04:00+00' ORDER BY id;
\echo === Q1-7 prior sessions baseline: screened / cap-only per scan date
SELECT scan_date, COUNT(DISTINCT ticker) screened, COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) cap_only FROM mi_ep_scan_log WHERE scan_date >= '2026-10-05' GROUP BY 1 ORDER BY 1;
\echo === Q1-8 strategy row + stop-switch row
SELECT strategy_id, phase, enabled, live_real_enabled, position_size_multiplier, max_concurrent_positions, profit_trigger_r, breakeven_arm_r, created_at, updated_at FROM mi_strategies WHERE strategy_id='magna53_smallcap';
SELECT * FROM mi_safeguard_state WHERE safeguard ILIKE '%lowcap%';
