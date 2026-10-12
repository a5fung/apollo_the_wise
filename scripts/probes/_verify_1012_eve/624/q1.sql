\echo === 1 heartbeat + lane audit rows 10-12 (full)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS t_et, event_type, summary, detail FROM mi_audit_log WHERE created_at >= '2026-10-12 04:00+00' AND (event_type ILIKE '%lowcap_paper%' OR event_type ILIKE '%paper_lane%') ORDER BY id;
\echo === 1b heartbeat rows ever (count, by day)
SELECT to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD') d, count(*) FROM mi_audit_log WHERE event_type='lowcap_paper_lane_heartbeat' GROUP BY 1 ORDER BY 1;
\echo === 1c any lowcap error/other audit event since 10-10 (all types)
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS t_et, event_type, left(summary,220) FROM mi_audit_log WHERE created_at >= '2026-10-10 12:00+00' AND (event_type ILIKE '%lowcap%' OR event_type ILIKE '%smallcap%' OR summary ILIKE '%magna53_smallcap%' OR summary ILIKE '%paper lane%' OR summary ILIKE '%small-cap%') ORDER BY id;
\echo === 2 lane table rows (all)
SELECT id, ticker, alert_date, strategy_id, to_char(first_graded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') fg, score_tier, reject_stage, reject_reason, round(gap_pct::numeric,1) gap, round(market_cap/1e6) mcap_m FROM mi_lowcap_paper_lane_alerts ORDER BY id;
\echo === 3 mi_ep_alerts: lane tickers present (join ticker+alert_date)
SELECT a.id, a.ticker, a.alert_date, a.score_tier FROM mi_ep_alerts a JOIN mi_lowcap_paper_lane_alerts l ON l.ticker=a.ticker AND l.alert_date=a.alert_date;
\echo === 3b mi_ep_alerts rows for ALLT any date since 10-01
SELECT id, ticker, alert_date, score_tier FROM mi_ep_alerts WHERE ticker='ALLT' AND alert_date >= '2026-10-01';
\echo === 3c mi_ep_alerts rows today (count, by tier) + yesterday-baseline
SELECT alert_date, score_tier, count(*) FROM mi_ep_alerts WHERE alert_date >= '2026-10-05' GROUP BY 1,2 ORDER BY 1,2;
\echo === 4 trades: any magna53_smallcap by account
SELECT account_mode, signal_type, count(*) FROM mi_live_trades WHERE signal_type='magna53_smallcap' GROUP BY 1,2;
\echo === 4b all trades created today by account/signal
SELECT account_mode, signal_type, count(*) FROM mi_live_trades WHERE created_at >= '2026-10-12 04:00+00' GROUP BY 1,2;
\echo === 4c trades w/ ticker ALLT any
SELECT id, ticker, signal_type, account_mode, status, alert_date FROM mi_live_trades WHERE ticker='ALLT' ORDER BY id DESC LIMIT 5;
\echo === 5 heartbeat SQL re-run at EOD (screened / cap-only / by-name)
SELECT COUNT(DISTINCT ticker) AS screened,
       COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) AS cap_only
FROM mi_ep_scan_log WHERE scan_date = '2026-10-12';
\echo === 5b scan log last tick + total ticks
SELECT to_char(max(created_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') last_row_et, count(DISTINCT scan_time_et) ticks, count(*) rows FROM mi_ep_scan_log WHERE scan_date='2026-10-12';
\echo === 5c cap-only name reject stages for any ticker with mcap<500M and decided at a later stage (names that reached other stage but cap)
SELECT ticker, reject_stage, left(filter_reason,100) fr, round(market_cap/1e6) mcap_m, round(gap_pct::numeric,1) gap FROM mi_ep_scan_log WHERE scan_date='2026-10-12' AND market_cap IS NOT NULL AND market_cap < 500e6 AND prev_close >= 5 AND gap_pct >= 9 ORDER BY ticker, id;
\echo === 6 paper lane replays
SELECT count(*) FROM mi_lowcap_paper_lane_replays;
\echo === 7 prior-day baseline: heartbeat-eligible cap-only names last 5 sessions (would have been 'ran'/'quiet')
SELECT scan_date, COUNT(DISTINCT ticker) screened, COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) cap_only FROM mi_ep_scan_log WHERE scan_date >= '2026-10-05' GROUP BY 1 ORDER BY 1;
