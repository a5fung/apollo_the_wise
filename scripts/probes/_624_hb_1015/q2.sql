\pset pager off
\echo === Q2-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === Q2-1 boot / deploy evidence 10-14 20:30 ET .. 10-15 00:30 ET (rows only a restart writes)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-10-15 00:30+00' AND created_at < '2026-10-15 04:30+00' AND event_type IN ('account_mode_active','dual_account_creds_resolved','drift_check_snapshot','boot_complete','preflight_ok','scheduler_started','llm_request_rewrite_adopted') ORDER BY id;
\echo === Q2-1b boot rows 10-15 ET (any further restart today?)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,120) FROM mi_audit_log WHERE created_at >= '2026-10-15 04:00+00' AND event_type IN ('account_mode_active','boot_complete','scheduler_started') ORDER BY id;
\echo === Q2-2 DROPPED-JOB SWEEP: job ids in the window after the 10-13 evening deploy-equivalent (10-13 21:20 ET -> 10-14 18:30 ET) vs the window after THIS deploy (10-14 21:20 ET -> 10-15 18:30 ET) whose run counts differ
WITH y AS (SELECT job_id, count(*) n FROM mi_job_runs WHERE started_at >= '2026-10-14 01:20+00' AND started_at < '2026-10-14 22:30+00' GROUP BY 1),
     t AS (SELECT job_id, count(*) n FROM mi_job_runs WHERE started_at >= '2026-10-15 01:20+00' AND started_at < '2026-10-15 22:30+00' GROUP BY 1)
SELECT COALESCE(y.job_id,t.job_id) job_id, COALESCE(y.n,0) wed_window, COALESCE(t.n,0) thu_window FROM y FULL JOIN t USING (job_id) WHERE COALESCE(y.n,0) <> COALESCE(t.n,0) ORDER BY 1;
\echo === Q2-2b same sweep, how many job ids match exactly
WITH y AS (SELECT job_id, count(*) n FROM mi_job_runs WHERE started_at >= '2026-10-14 01:20+00' AND started_at < '2026-10-14 22:30+00' GROUP BY 1),
     t AS (SELECT job_id, count(*) n FROM mi_job_runs WHERE started_at >= '2026-10-15 01:20+00' AND started_at < '2026-10-15 22:30+00' GROUP BY 1)
SELECT count(*) FILTER (WHERE y.n = t.n) same_count, count(*) FILTER (WHERE y.n IS NULL) only_thu, count(*) FILTER (WHERE t.n IS NULL) only_wed, count(*) total_job_ids FROM y FULL JOIN t USING (job_id);
\echo === Q2-3 non-success job runs since the deploy (10-14 21:00 ET onward)
SELECT id, job_id, to_char(started_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') st_et, status, left(error_message,200) err FROM mi_job_runs WHERE started_at >= '2026-10-15 01:00+00' AND status <> 'success' ORDER BY id;
\echo === Q2-4 ep_scan job durations inside ORB window 09:25-10:00 ET, by day
SELECT to_char(started_at AT TIME ZONE 'America/New_York','MM-DD') d, count(*) n, round(min(duration_s)::numeric,2) mn, round(max(duration_s)::numeric,2) mx, round(avg(duration_s)::numeric,2) av, count(*) FILTER (WHERE status<>'success') nonok FROM mi_job_runs WHERE job_id='ep_scan' AND started_at >= '2026-10-05 04:00+00' AND (started_at AT TIME ZONE 'America/New_York')::time BETWEEN '09:25' AND '10:00' GROUP BY 1 ORDER BY 1;
\echo === Q2-4b ep_scan_open + ep_scan rows 10-15 ET 09:25-10:00
SELECT job_id, to_char(started_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') st, round(duration_s::numeric,2) dur, status FROM mi_job_runs WHERE job_id IN ('ep_scan','ep_scan_open') AND started_at >= '2026-10-15 13:25+00' AND started_at < '2026-10-15 14:01+00' ORDER BY id;
\echo === Q2-5 live-path rows that reached grading 09:30-09:55 ET on 10-15
SELECT ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS') t_et, reject_stage, left(filter_reason,120) fr, round(gap_pct::numeric,1) gap, round(market_cap/1e6) mcap_m, ep_score, score_tier FROM mi_ep_scan_log WHERE scan_date='2026-10-15' AND (scan_time_et AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '09:55' AND reject_stage NOT IN ('gap_floor','universe_floor') ORDER BY scan_time_et, ticker;
\echo === Q2-5b live scan stage breakdown 10-15 whole day
SELECT reject_stage, count(*) n, count(DISTINCT ticker) tk FROM mi_ep_scan_log WHERE scan_date='2026-10-15' GROUP BY 1 ORDER BY 2 DESC;
\echo === Q2-5c any scored row (ep_score not null) in the live scan log 10-15
SELECT ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') t_et, reject_stage, ep_score, score_tier, catalyst_quality, llm_catalyst_quality FROM mi_ep_scan_log WHERE scan_date='2026-10-15' AND ep_score IS NOT NULL ORDER BY id;
\echo === Q2-6 judge timeout / late grade / refusal audit rows since 10-15 00:00 ET
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-10-15 04:00+00' AND (event_type ILIKE '%judge%timeout%' OR event_type ILIKE '%late_grade%' OR summary ILIKE '%judge%timeout%' OR summary ILIKE '%timed out%') ORDER BY id LIMIT 40;
\echo === Q2-7 live-path provenance/admit rows 10-15
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t_et, event_type, left(summary,200) s FROM mi_audit_log WHERE created_at >= '2026-10-15 04:00+00' AND event_type IN ('ep_rt_admit','ep_catalyst_provenance','ep_rt_shadow_capture','ep_rt_universe_catch') ORDER BY id;
\echo === Q2-8 any audit row 10-15 mentioning paper lane / magna53_smallcap / small-cap
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t_et, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-10-15 04:00+00' AND event_type NOT IN ('lowcap_paper_lane_tick') AND (summary ILIKE '%paper lane%' OR summary ILIKE '%magna53_smallcap%' OR summary ILIKE '%small-cap%') ORDER BY id;
\echo === Q2-9 audit error-class rows since the deploy (10-14 21:00 ET onward)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-10-15 01:00+00' AND (event_type ILIKE '%fail%' OR event_type ILIKE '%error%') ORDER BY id LIMIT 40;
\echo === Q2-10 api_usage ep_catalyst_grade calls 10-15 by ET minute-bucket (08:00-10:00) and day totals
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI') m_et, caller, count(*) n, round(sum(cost_usd)::numeric,4) cost, string_agg(DISTINCT stop_reason, ',') stops FROM api_usage WHERE caller IN ('ep_catalyst_grade','lowcap_paper_lane_judge','ep_grade_judge') AND created_at >= '2026-10-15 11:00+00' AND created_at < '2026-10-15 22:30+00' GROUP BY 1,2 ORDER BY 1,2;
\echo === Q2-10b ep_catalyst_grade calls per ET day last 7 days
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD') d, count(*) n, round(sum(cost_usd)::numeric,3) cost FROM api_usage WHERE caller='ep_catalyst_grade' AND created_at >= '2026-10-07 04:00+00' GROUP BY 1 ORDER BY 1;
