\pset pager off
\echo === V1-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === V1-1 every audit row whose summary starts '2026-10-14' for the heartbeat event, plus any heartbeat row created 10-14 ET (dupes / rehearsal)
SELECT id, event_type, to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS.MS') c_et, created_at > '2026-10-14 16:03:28+00' AS after_market_boot, detail::jsonb->>'verdict' verdict, (detail::jsonb->>'screened')::int screened, detail::jsonb->>'cap_only_eligible' cap_only, detail::jsonb->'missing' missing, detail::jsonb->>'lane_enabled' lane_enabled FROM mi_audit_log WHERE event_type='lowcap_paper_lane_heartbeat' AND (summary LIKE '2026-10-14%' OR (created_at AT TIME ZONE 'America/New_York')::date = '2026-10-14') ORDER BY id;
\echo === V1-2 mi_job_runs columns
SELECT column_name FROM information_schema.columns WHERE table_name='mi_job_runs' ORDER BY ordinal_position;
\echo === V1-3 the 10-14 lowcap_lane_replay job run (all columns)
SELECT * FROM mi_job_runs WHERE job_id='lowcap_lane_replay' AND started_at >= '2026-10-14 04:00+00';
\echo === V1-4 independent screened/cap-only: distinct tickers 10-14 by ET created date vs scan_date, and ANY row mentioning mcap / market cap on 10-12..10-14, any stage
SELECT scan_date, count(DISTINCT ticker) screened_by_scan_date, count(DISTINCT ticker) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::date = scan_date) screened_created_same_et_day, count(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::date <> scan_date) rows_off_day FROM mi_ep_scan_log WHERE scan_date BETWEEN '2026-10-12' AND '2026-10-14' GROUP BY 1 ORDER BY 1;
SELECT scan_date, ticker, reject_stage, left(filter_reason,120) fr, count(*) FROM mi_ep_scan_log WHERE scan_date BETWEEN '2026-10-12' AND '2026-10-14' AND (filter_reason ILIKE '%mcap%' OR filter_reason ILIKE '%market cap%' OR filter_reason ILIKE '%500M%') GROUP BY 1,2,3,4 ORDER BY 1,2;
\echo === V1-5 any 10-14 scan row with a non-null market_cap under 500M (any stage, any price, any gap)
SELECT ticker, reject_stage, round(market_cap/1e6) mcap_m, round(max(gap_pct)::numeric,1) max_gap, round(max(prev_close)::numeric,2) pc, count(*) FROM mi_ep_scan_log WHERE scan_date='2026-10-14' AND market_cap IS NOT NULL AND market_cap < 500e6 GROUP BY 1,2,3 ORDER BY 1;
\echo === V1-6 quality_filter tickers 10-14 with their distinct filter reasons
SELECT ticker, array_agg(DISTINCT split_part(filter_reason,':',3)) reasons, count(*) FROM mi_ep_scan_log WHERE scan_date='2026-10-14' AND reject_stage='quality_filter' GROUP BY 1 ORDER BY 1;
\echo === V1-7 lane table: any row dated 10-14 or graded on 10-14 ET
SELECT id, ticker, alert_date, to_char(first_graded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') fg FROM mi_lowcap_paper_lane_alerts WHERE alert_date='2026-10-14' OR (first_graded_at AT TIME ZONE 'America/New_York')::date='2026-10-14' OR (last_graded_at AT TIME ZONE 'America/New_York')::date='2026-10-14';
SELECT count(*) total_lane_rows FROM mi_lowcap_paper_lane_alerts;
\echo === V1-8 lane tick / error audit rows created 10-14 ET, and error rows ever
SELECT event_type, count(*) FROM mi_audit_log WHERE event_type IN ('lowcap_paper_lane_tick','lowcap_paper_lane_error') AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-14' GROUP BY 1;
SELECT count(*) lane_error_rows_ever FROM mi_audit_log WHERE event_type='lowcap_paper_lane_error';
\echo === V1-9 WOULD-FAIL-IF arms: lane ticker+date in mi_ep_alerts (ever); smallcap trades (any account); non-live trades created since 10-10
SELECT count(*) lane_rows_in_ep_alerts FROM mi_ep_alerts a JOIN mi_lowcap_paper_lane_alerts l USING (ticker, alert_date);
SELECT account_mode, signal_type, count(*) FROM mi_live_trades WHERE signal_type ILIKE '%smallcap%' OR signal_type ILIKE '%lowcap%' OR (account_mode <> 'live' AND created_at >= '2026-10-10 04:00+00') GROUP BY 1,2;
\echo === V1-10 toggle override row and strategy row (the heartbeat's enabled inputs)
SELECT safeguard, account_mode, state, updated_at FROM mi_safeguard_state WHERE safeguard='lowcap_paper_lane';
SELECT strategy_id, phase, enabled, updated_at FROM mi_strategies WHERE strategy_id='magna53_smallcap';
\echo === V1-11 dropped-job sweep, Wed vs Wed: job ids that ran Wed 10-07 12:06-18:30 ET but not Wed 10-14 same window (catches weekday-specific jobs)
WITH a AS (SELECT DISTINCT job_id FROM mi_job_runs WHERE started_at >= '2026-10-07 16:06+00' AND started_at < '2026-10-07 22:30+00'),
     b AS (SELECT DISTINCT job_id FROM mi_job_runs WHERE started_at >= '2026-10-14 16:06+00' AND started_at < '2026-10-14 22:30+00')
SELECT 'only_wed_10_07' side, job_id FROM a WHERE job_id NOT IN (SELECT job_id FROM b)
UNION ALL SELECT 'only_wed_10_14', job_id FROM b WHERE job_id NOT IN (SELECT job_id FROM a) ORDER BY 1,2;
SELECT (SELECT count(DISTINCT job_id) FROM mi_job_runs WHERE started_at >= '2026-10-07 16:06+00' AND started_at < '2026-10-07 22:30+00') wed_1007_ids, (SELECT count(DISTINCT job_id) FROM mi_job_runs WHERE started_at >= '2026-10-14 16:06+00' AND started_at < '2026-10-14 22:30+00') wed_1014_ids;
\echo === V1-12 lowcap_lane_replay run every weekday since lane go-live (a gap = a dropped run)
SELECT (started_at AT TIME ZONE 'America/New_York')::date d, to_char(started_at AT TIME ZONE 'America/New_York','Dy HH24:MI') t, status FROM mi_job_runs WHERE job_id='lowcap_lane_replay' AND started_at >= '2026-10-05 04:00+00' ORDER BY 1;
