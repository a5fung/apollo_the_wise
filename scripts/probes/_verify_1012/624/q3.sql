\echo === heartbeat preview (same SQL as write_paper_lane_heartbeat) screened / cap_only
SELECT COUNT(DISTINCT ticker) AS screened,
       COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'market cap') > 0), ARRAY[]::text[]) AS cap_only_probe
FROM mi_ep_scan_log WHERE scan_date = '2026-10-12';
\echo === mcap reason text constant check
SELECT DISTINCT left(filter_reason, 120) FROM mi_ep_scan_log WHERE scan_date = '2026-10-12' AND reject_stage='quality_filter' AND filter_reason ILIKE '%cap%' LIMIT 10;
\echo === cap-only names today w/ scan time
SELECT ticker, left(filter_reason,110) fr, to_char(min(scanned_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') first_seen, to_char(max(scanned_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') last_seen, count(*) n FROM mi_ep_scan_log WHERE scan_date='2026-10-12' AND reject_stage='quality_filter' AND filter_reason ILIKE '%cap%' GROUP BY 1,2 ORDER BY 1;
\echo === scan log last tick today
SELECT to_char(max(scanned_at) AT TIME ZONE 'America/New_York','HH24:MI:SS') last_scan, count(DISTINCT ticker) tickers, count(*) rows FROM mi_ep_scan_log WHERE scan_date='2026-10-12';
\echo === paper trades any today / account modes of today live trades
SELECT account_mode, signal_type, count(*) FROM mi_live_trades WHERE alert_date='2026-10-12' GROUP BY 1,2;
\echo === live-book orders w/ lane signal_type ever
SELECT account_mode, count(*) FROM mi_live_trades WHERE signal_type='magna53_smallcap' GROUP BY 1;
\echo === lane audit rows other types since 10-10
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t, event_type, left(summary,160) FROM mi_audit_log WHERE created_at > '2026-10-10 12:00+00' AND event_type IN ('lowcap_paper_lane_error','lowcap_paper_lane_tick','lowcap_paper_lane_heartbeat','lowcap_paper_lane_order','lowcap_paper_lane_skip') ORDER BY created_at;
