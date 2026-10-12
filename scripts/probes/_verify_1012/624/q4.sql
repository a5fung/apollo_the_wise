\echo === columns
SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_scan_log' ORDER BY ordinal_position;
\echo === heartbeat preview (exact SQL)
SELECT COUNT(DISTINCT ticker) AS screened,
       COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) AS cap_only
FROM mi_ep_scan_log WHERE scan_date = '2026-10-12';
\echo === lane rows today
SELECT ticker, score_tier, reject_stage FROM mi_lowcap_paper_lane_alerts WHERE alert_date='2026-10-12';
\echo === same preview for prior days (cap_only counts/names) 10-05..10-09
SELECT scan_date, COUNT(DISTINCT ticker) screened, COALESCE(array_agg(DISTINCT ticker) FILTER (WHERE reject_stage = 'quality_filter' AND strpos(filter_reason, 'filter:mcap_too_small') > 0), ARRAY[]::text[]) cap_only FROM mi_ep_scan_log WHERE scan_date >= '2026-10-01' GROUP BY 1 ORDER BY 1;
