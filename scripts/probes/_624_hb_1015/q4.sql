\pset pager off
\echo === Q4-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === Q4-1 re-run of Q3-1b (it errored on a round cast): inputs of BETR lane row vs DFH live row - different inputs bucketing to the same score = coincidence, same inputs = contamination
SELECT 'lane BETR' src, gap_pct::numeric(6,2) gap, rel_volume::numeric(6,2) rv, pm_rvol::numeric(6,2) pmrv, current_price::numeric(8,2) px, prev_close::numeric(8,2) pc, atr_pct::numeric(5,1) atr, (quality_adv_dollar/1e6)::numeric(8,1) adv_m, (market_cap/1e6)::numeric(8,0) mcap_m, in_active_theme, catalyst_quality FROM mi_lowcap_paper_lane_alerts WHERE ticker='BETR' AND alert_date='2026-10-15'
UNION ALL
SELECT 'live DFH', gap_pct::numeric(6,2), rel_volume::numeric(6,2), pm_rvol::numeric(6,2), current_price::numeric(8,2), prev_close::numeric(8,2), atr_pct::numeric(5,1), (quality_adv_dollar/1e6)::numeric(8,1), (market_cap/1e6)::numeric(8,0), in_active_theme, catalyst_quality FROM (SELECT * FROM mi_ep_scan_log WHERE ticker='DFH' AND scan_date='2026-10-15' AND ep_score IS NOT NULL ORDER BY id DESC LIMIT 1) d;
\echo === Q4-2 does the scoring formula bucket (same breakdown different gap gives the same score)? other 10-15 live rows with breakdown gap 10 float 5 and nothing else
SELECT ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') t_et, ep_score, gap_pct::numeric(6,2) gap, score_breakdown::text FROM mi_ep_scan_log WHERE scan_date='2026-10-15' AND ep_score IS NOT NULL AND ticker <> 'ERIC' ORDER BY id;
\echo === Q4-3 lane BETR row full tail (all time stamps and reject fields)
SELECT id, ticker, to_char(first_graded_at AT TIME ZONE 'America/New_York','HH24:MI:SS') fg, to_char(last_graded_at AT TIME ZONE 'America/New_York','HH24:MI:SS') lg, to_char(detected_at AT TIME ZONE 'America/New_York','HH24:MI:SS') det, reject_stage, reject_reason, ep_score, baseline_floor_tier, grade_engine_authority, setup_class, rubric_version, regime FROM mi_lowcap_paper_lane_alerts WHERE alert_date='2026-10-15' ORDER BY id;
