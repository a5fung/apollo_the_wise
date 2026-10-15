\pset pager off
\echo === Q0-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === Q0-1 columns of mi_lowcap_paper_lane_alerts
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_lowcap_paper_lane_alerts' ORDER BY ordinal_position;
\echo === Q0-2 columns of api_usage
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='api_usage' ORDER BY ordinal_position;
\echo === Q0-3 columns of mi_ep_scan_log
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_ep_scan_log' ORDER BY ordinal_position;
