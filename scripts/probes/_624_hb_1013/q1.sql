\echo === 0 now (ET) + heartbeat/lane audit rows since 10-12 18:00 ET (full)
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS t_et, event_type, summary, detail FROM mi_audit_log WHERE created_at >= '2026-10-12 22:00+00' AND (event_type ILIKE '%lowcap%' OR event_type ILIKE '%paper_lane%' OR event_type ILIKE '%smallcap%') ORDER BY id;
\echo === 1 heartbeat rows ever (count by ET day, ids)
SELECT to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD') d, count(*) n, min(id) min_id, max(id) max_id FROM mi_audit_log WHERE event_type='lowcap_paper_lane_heartbeat' GROUP BY 1 ORDER BY 1;
\echo === 1b any lane error / page-class row since ship (10-10 12:00 UTC)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,240) FROM mi_audit_log WHERE created_at >= '2026-10-10 12:00+00' AND (event_type = 'lowcap_paper_lane_error' OR (event_type ILIKE '%lowcap%' AND (summary ILIKE '%fail%' OR summary ILIKE '%error%' OR summary ILIKE '%broken%' OR summary ILIKE '%timeout%'))) ORDER BY id;
\echo === 1c lane tick rows (all days)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, summary, detail FROM mi_audit_log WHERE event_type='lowcap_paper_lane_tick' ORDER BY id;
\echo === 2 lane table rows (all)
SELECT id, ticker, alert_date, strategy_id, to_char(first_graded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') fg, to_char(last_graded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') lg, score_tier, ep_score, reject_stage, reject_reason, round(gap_pct::numeric,1) gap, round(market_cap/1e6) mcap_m, catalyst_quality, judge_tier FROM mi_lowcap_paper_lane_alerts ORDER BY id;
\echo === 3 mi_ep_alerts rows matching a lane ticker+date (must be 0)
SELECT a.id, a.ticker, a.alert_date, a.score_tier FROM mi_ep_alerts a JOIN mi_lowcap_paper_lane_alerts l ON l.ticker=a.ticker AND l.alert_date=a.alert_date;
\echo === 3b mi_ep_alerts by date/tier 10-05..today (live-path baseline)
SELECT alert_date, score_tier, count(*) FROM mi_ep_alerts WHERE alert_date >= '2026-10-05' GROUP BY 1,2 ORDER BY 1,2;
\echo === 3c mi_ep_alerts today rows
SELECT id, ticker, alert_date, score_tier, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t_et FROM mi_ep_alerts WHERE alert_date = '2026-10-13' ORDER BY id;
\echo === 4 trades: magna53_smallcap ever, by account
SELECT account_mode, signal_type, status, count(*) FROM mi_live_trades WHERE signal_type='magna53_smallcap' GROUP BY 1,2,3;
\echo === 4b all trades created since 10-12 ET by account/signal/status
SELECT account_mode, signal_type, status, count(*) FROM mi_live_trades WHERE created_at >= '2026-10-12 04:00+00' GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo === 4c any trade whose order id mentions smallcap or any trade whose ticker is a lane ticker
SELECT t.id, t.ticker, t.signal_type, t.account_mode, t.status, t.alert_date, t.entry_order_id FROM mi_live_trades t WHERE t.entry_order_id ILIKE '%smallcap%' OR t.ticker IN (SELECT ticker FROM mi_lowcap_paper_lane_alerts) ORDER BY t.id DESC LIMIT 10;
\echo === 5 heartbeat SQL re-run at EOD (screened / cap-only)
SELECT COUNT(DISTINCT ticker) AS screened,
       COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) AS cap_only
FROM mi_ep_scan_log WHERE scan_date = '2026-10-13';
\echo === 5b scan log last row + ticks
SELECT to_char(max(created_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') last_row_et, count(DISTINCT scan_time_et) ticks, count(*) nrows FROM mi_ep_scan_log WHERE scan_date='2026-10-13';
\echo === 5c sub-500M, $5+, gap>=9 names on scan log today with stage
SELECT ticker, reject_stage, left(filter_reason,100) fr, round(market_cap/1e6) mcap_m, round(gap_pct::numeric,1) gap, round(prev_close::numeric,2) pc, scan_time_et FROM mi_ep_scan_log WHERE scan_date='2026-10-13' AND market_cap IS NOT NULL AND market_cap < 500e6 AND prev_close >= 5 AND gap_pct >= 9 ORDER BY ticker, id;
\echo === 5d ALL mcap_too_small-stamped names today (incl. any pre-$5 / low-gap)
SELECT DISTINCT ticker, round(market_cap/1e6) mcap_m, round(gap_pct::numeric,1) gap, round(prev_close::numeric,2) pc FROM mi_ep_scan_log WHERE scan_date='2026-10-13' AND strpos(filter_reason, 'filter:mcap_too_small') > 0 ORDER BY 1;
\echo === 6 paper lane replays
SELECT count(*) FROM mi_lowcap_paper_lane_replays;
\echo === 7 prior sessions baseline: screened / cap-only per scan date
SELECT scan_date, COUNT(DISTINCT ticker) screened, COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) cap_only FROM mi_ep_scan_log WHERE scan_date >= '2026-10-05' GROUP BY 1 ORDER BY 1;
\echo === 8 strategy row
SELECT * FROM mi_strategies WHERE strategy_id ILIKE '%smallcap%' OR id::text ILIKE '%smallcap%';
\echo === 9 job-run cols
SELECT column_name FROM information_schema.columns WHERE table_name='mi_job_runs' ORDER BY ordinal_position;
\echo === 9b lowcap / ep-scan job runs since 10-12 ET
SELECT id, job_id, to_char(started_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') st_et, duration_s, status, rows_written, left(error_message,160) err FROM mi_job_runs WHERE started_at >= '2026-10-12 04:00+00' AND (job_id ILIKE '%lowcap%' OR job_id ILIKE '%paper_lane%') ORDER BY id;
\echo === 9c ep scan job_id names today
SELECT job_id, count(*), min(duration_s), max(duration_s), round(avg(duration_s)::numeric,1) avg_s, count(*) FILTER (WHERE status<>'success') nonok FROM mi_job_runs WHERE started_at >= '2026-10-13 04:00+00' AND (job_id ILIKE '%ep_scan%' OR job_id ILIKE '%ep%scan%' OR job_id ILIKE '%run_ep%') GROUP BY 1;
\echo === 10 live-scan judge timeout / late grade audit rows 10-13 and 10-12 ORB window
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-10-12 04:00+00' AND (event_type ILIKE '%judge%' OR event_type ILIKE '%timeout%' OR summary ILIKE '%judge%timeout%' OR summary ILIKE '%timed out%' OR event_type ILIKE '%late_grade%') ORDER BY id LIMIT 40;
\echo === 11 all audit event types logged today (counts) for a scan of anything new
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at >= '2026-10-13 04:00+00' GROUP BY 1 ORDER BY 2 DESC LIMIT 60;
