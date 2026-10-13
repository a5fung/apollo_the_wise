\pset pager off
\echo === A now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === B every heartbeat row ever (full)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') t_et, summary, detail FROM mi_audit_log WHERE event_type='lowcap_paper_lane_heartbeat' ORDER BY id;
\echo === B2 heartbeat verdict tally (any non ran/quiet ever?)
SELECT detail::jsonb->>'verdict' verdict, count(*) FROM mi_audit_log WHERE event_type='lowcap_paper_lane_heartbeat' GROUP BY 1;
\echo === C every lowcap-ish audit event type since 10-10 00:00 ET (counts)
SELECT event_type, count(*), min(to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI')) first_et, max(to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI')) last_et FROM mi_audit_log WHERE created_at >= '2026-10-10 04:00+00' AND (event_type ILIKE '%lowcap%' OR event_type ILIKE '%smallcap%' OR event_type ILIKE '%paper_lane%') GROUP BY 1 ORDER BY 1;
\echo === C2 any lowcap_paper_lane_error ever
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, summary FROM mi_audit_log WHERE event_type='lowcap_paper_lane_error' ORDER BY id;
\echo === D replay job runs since 10-09 ET
SELECT id, job_id, to_char(started_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') st_et, to_char(finished_at AT TIME ZONE 'America/New_York','HH24:MI:SS') fin_et, round(duration_s::numeric,3) dur, status, left(error_message,120) err FROM mi_job_runs WHERE job_id ILIKE '%lowcap%' AND started_at >= '2026-10-09 04:00+00' ORDER BY id;
\echo === E heartbeat screened SQL, verbatim, 10-12 and 10-13
SELECT '2026-10-13' d, COUNT(DISTINCT ticker) AS screened, COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) AS cap_only FROM mi_ep_scan_log WHERE scan_date = '2026-10-13'::date
UNION ALL
SELECT '2026-10-12', COUNT(DISTINCT ticker), COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) FROM mi_ep_scan_log WHERE scan_date = '2026-10-12'::date;
\echo === E2 scan log 10-13: rows, ticks, first/last row ET, rows created after 18:15 ET (late writes after the heartbeat?)
SELECT count(*) nrows, count(DISTINCT scan_time_et) ticks, to_char(min(created_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') first_et, to_char(max(created_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') last_et, count(*) FILTER (WHERE created_at >= '2026-10-13 22:15+00') after_hb FROM mi_ep_scan_log WHERE scan_date='2026-10-13';
\echo === F lane table columns
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_lowcap_paper_lane_alerts' ORDER BY ordinal_position;
\echo === F2 lane table population (all rows, by strategy/date)
SELECT strategy_id, alert_date, count(*), array_agg(ticker ORDER BY id) tickers, array_agg(id ORDER BY id) ids FROM mi_lowcap_paper_lane_alerts GROUP BY 1,2 ORDER BY 2;
\echo === F3 lane rows heartbeat SQL verbatim 10-13
SELECT ticker, score_tier, reject_stage FROM mi_lowcap_paper_lane_alerts WHERE alert_date = '2026-10-13'::date;
\echo === G mi_ep_alerts: lane tickers on any date; any alert dated or created 10-12/10-13
SELECT id, ticker, alert_date, score_tier, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') c_et FROM mi_ep_alerts WHERE ticker IN (SELECT ticker FROM mi_lowcap_paper_lane_alerts) ORDER BY id DESC LIMIT 10;
SELECT count(*) FILTER (WHERE alert_date IN ('2026-10-12','2026-10-13')) by_alert_date, count(*) FILTER (WHERE created_at >= '2026-10-12 04:00+00') by_created FROM mi_ep_alerts;
\echo === G2 last 5 mi_ep_alerts rows (is the table live at all?)
SELECT id, ticker, alert_date, score_tier, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') c_et FROM mi_ep_alerts ORDER BY id DESC LIMIT 5;
\echo === H mi_live_trades columns
SELECT column_name FROM information_schema.columns WHERE table_name='mi_live_trades' ORDER BY ordinal_position;
\echo === H2 lane strategy trades ever / lane tickers / dated 10-12..13
SELECT id, ticker, signal_type, account_mode, status, alert_date, entry_order_id FROM mi_live_trades WHERE signal_type='magna53_smallcap' OR ticker IN (SELECT ticker FROM mi_lowcap_paper_lane_alerts) OR alert_date >= '2026-10-12' ORDER BY id DESC LIMIT 20;
\echo === H3 last 8 trades by id (what is the newest trade at all?)
SELECT id, ticker, signal_type, account_mode, status, alert_date, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') c_et, left(entry_order_id,40) eoid FROM mi_live_trades ORDER BY id DESC LIMIT 8;
\echo === I today's entry_partial_fill / paper_rehearsal_687_state / trade_lifecycle rows (tickers)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t_et, event_type, left(summary,220) FROM mi_audit_log WHERE created_at >= '2026-10-13 04:00+00' AND event_type IN ('entry_partial_fill','paper_rehearsal_687_state','trade_lifecycle_telegram_attempted','order_status_reconciled','entry_rejection_watch_armed','account_mode_active') ORDER BY id;
\echo === J strategy row + toggle
SELECT strategy_id, phase, enabled, live_real_enabled, position_size_multiplier, max_concurrent_positions, profit_trigger_r, breakeven_arm_r, created_at, updated_at FROM mi_strategies WHERE strategy_id='magna53_smallcap';
SELECT column_name FROM information_schema.columns WHERE table_name='mi_safeguard_state' ORDER BY ordinal_position;
SELECT * FROM mi_safeguard_state WHERE (mi_safeguard_state)::text ILIKE '%lowcap%';
\echo === K 09:31 open-scan run 10-13 vs EFXT fresh grade
SELECT job_id, to_char(started_at AT TIME ZONE 'America/New_York','HH24:MI:SS') st, to_char(finished_at AT TIME ZONE 'America/New_York','HH24:MI:SS') fin, round(duration_s::numeric,2) dur, status FROM mi_job_runs WHERE started_at >= '2026-10-13 13:25+00' AND started_at < '2026-10-13 14:00+00' AND job_id ILIKE 'ep_scan%' ORDER BY started_at;
