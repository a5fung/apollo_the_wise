\pset pager off
\echo === V1-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === V1-1 vol_percentile parity: lane rows vs live graded rows 10-15 (lane 0.0 is a defect only if live graded names never read 0)
SELECT 'lane' src, ticker, to_char(last_graded_at AT TIME ZONE 'America/New_York','HH24:MI') t_et, vol_percentile::numeric(6,1) vp, rel_volume::numeric(6,2) rv, score_breakdown->>'vol_conviction' vc FROM mi_lowcap_paper_lane_alerts WHERE alert_date >= '2026-10-12' 
UNION ALL
SELECT 'live', ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI'), vol_percentile::numeric(6,1), rel_volume::numeric(6,2), score_breakdown->>'vol_conviction' FROM mi_ep_scan_log WHERE scan_date='2026-10-15' AND reject_stage IN ('score_bar','post_grade_filter') AND (scan_time_et AT TIME ZONE 'America/New_York')::time >= '09:30'
ORDER BY 1,2,3;
\echo === V1-2 api_usage ep_catalyst_grade 10-15 exact timestamps vs provenance rows
SELECT 'api' src, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t_et, stop_reason, NULL::text s FROM api_usage WHERE caller='ep_catalyst_grade' AND created_at >= '2026-10-15 04:00+00' AND created_at < '2026-10-16 04:00+00'
UNION ALL
SELECT 'prov', to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS'), NULL, summary FROM mi_audit_log WHERE event_type='ep_catalyst_provenance' AND created_at >= '2026-10-15 04:00+00' AND created_at < '2026-10-16 04:00+00'
ORDER BY 2,1;
\echo === V1-3 ep_scan job finish times 09:40 and 09:45 vs BETR lane grade (lane runs after the live scan, detached)
SELECT job_id, to_char(started_at AT TIME ZONE 'America/New_York','HH24:MI:SS') st, to_char(finished_at AT TIME ZONE 'America/New_York','HH24:MI:SS.MS') fin, status FROM mi_job_runs WHERE job_id='ep_scan' AND started_at >= '2026-10-15 13:39+00' AND started_at < '2026-10-15 13:46+00' ORDER BY id;
\echo === V1-4 P15 shadow recorder (the other #624 half): signals by session since 10-01
SELECT session_date, count(*) FROM mi_lowcap_lane_signals WHERE session_date >= '2026-10-01' GROUP BY 1 ORDER BY 1;
SELECT count(*) total, max(session_date) last_session FROM mi_lowcap_lane_signals;
\echo === V1-5 lane rows ever with a non-paper strategy or a tier (must be magna53_smallcap only; tier any = first HIGH)
SELECT strategy_id, score_tier, count(*) FROM mi_lowcap_paper_lane_alerts GROUP BY 1,2;
