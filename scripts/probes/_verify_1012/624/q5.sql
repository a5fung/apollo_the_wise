\echo === ALLT in live scan log today (by tick)
SELECT scan_time_et, reject_stage, left(filter_reason,90) fr, round(gap_pct::numeric,1) gap, round(rel_volume::numeric,2) rv, round(market_cap/1e6) mcap_m FROM mi_ep_scan_log WHERE scan_date='2026-10-12' AND ticker='ALLT' ORDER BY id;
\echo === lane row detail
SELECT id, ticker, to_char(first_graded_at AT TIME ZONE 'America/New_York','HH24:MI:SS') fg, to_char(last_graded_at AT TIME ZONE 'America/New_York','HH24:MI:SS') lg, reject_stage, reject_reason, catalyst_quality, llm_catalyst_quality, round(vol_percentile::numeric,1) volpct, round(extension_pct::numeric,1) FROM mi_lowcap_paper_lane_alerts l LEFT JOIN LATERAL (SELECT max(extension_pct) extension_pct FROM mi_ep_scan_log s WHERE s.scan_date=l.alert_date AND s.ticker=l.ticker) x ON true;
\echo === scan ticks today (distinct scan_time_et count + last)
SELECT count(DISTINCT scan_time_et), min(scan_time_et), max(scan_time_et) FROM mi_ep_scan_log WHERE scan_date='2026-10-12';
\echo === paper account positions/orders unaffected: mi_live_trades paper recent
SELECT account_mode, signal_type, status, count(*) FROM mi_live_trades WHERE created_at > now() - interval '3 days' GROUP BY 1,2,3 ORDER BY 1,2,3;
