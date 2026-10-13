\echo === 1 mi_strategies cols
SELECT column_name FROM information_schema.columns WHERE table_name='mi_strategies' ORDER BY ordinal_position;
\echo === 1b smallcap strategy row (select * by name-ish text match)
SELECT s.* FROM mi_strategies s WHERE s::text ILIKE '%smallcap%';
\echo === 2 replay table cols + rows
SELECT column_name FROM information_schema.columns WHERE table_name='mi_lowcap_paper_lane_replays' ORDER BY ordinal_position;
SELECT * FROM mi_lowcap_paper_lane_replays ORDER BY 1;
\echo === 3 live-path admit/provenance rows today (full)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,300) s, left(detail,500) d FROM mi_audit_log WHERE created_at >= '2026-10-12 04:00+00' AND event_type IN ('ep_rt_admit','ep_catalyst_provenance','ep_rt_shadow_capture','ep_rt_universe_catch') ORDER BY id;
\echo === 4 ep_scan job durations inside ORB window 09:25-10:00 ET, by day (baseline 10-05..10-09 vs lane-live 10-12/10-13)
SELECT to_char(started_at AT TIME ZONE 'America/New_York','MM-DD') d, count(*) n, round(min(duration_s)::numeric,2) mn, round(max(duration_s)::numeric,2) mx, round(avg(duration_s)::numeric,2) av, count(*) FILTER (WHERE status<>'success') nonok
FROM mi_job_runs WHERE job_id='ep_scan' AND started_at >= '2026-10-05 04:00+00'
 AND (started_at AT TIME ZONE 'America/New_York')::time BETWEEN '09:25' AND '10:00'
GROUP BY 1 ORDER BY 1;
\echo === 4b ep_scan_open runs by day
SELECT to_char(started_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') st, round(duration_s::numeric,2) dur, status FROM mi_job_runs WHERE job_id='ep_scan_open' AND started_at >= '2026-10-05 04:00+00' ORDER BY id;
\echo === 5 scan log stage breakdown inside ORB window 09:30-09:45 ET, by day 10-07..10-13
SELECT scan_date, reject_stage, count(*) n, count(DISTINCT ticker) tk FROM mi_ep_scan_log WHERE scan_date >= '2026-10-07' AND (scan_time_et AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '09:45' GROUP BY 1,2 ORDER BY 1,2;
\echo === 5b GOSS all rows today
SELECT to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS') t_et, reject_stage, left(filter_reason,70) fr, round(gap_pct::numeric,1) gap, round(market_cap/1e6) mcap FROM mi_ep_scan_log WHERE scan_date='2026-10-13' AND ticker='GOSS' ORDER BY id;
\echo === 5c live names that got past quality_filter today (stage + reason)
SELECT ticker, reject_stage, left(filter_reason,90) fr, count(*) n, min(to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI')) first_t FROM mi_ep_scan_log WHERE scan_date='2026-10-13' AND reject_stage NOT IN ('quality_filter') GROUP BY 1,2,3 ORDER BY first_t, 1 LIMIT 40;
\echo === 6 paper-lane Telegram-page proxy: any audit event today with paper-prefix text
SELECT id, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-10-13 04:00+00' AND (summary ILIKE '%paper lane%' OR summary ILIKE '%magna53_smallcap%') ORDER BY id;
