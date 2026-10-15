\pset pager off
\echo === V2-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === V2-1 columns of mi_lowcap_lane_signals (the P15 shadow recorder)
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_lowcap_lane_signals' ORDER BY ordinal_position;
\echo === V2-2 P15 signals: total + by scan date since 10-01 (uses created_at ET date, column-agnostic)
SELECT count(*) total, to_char(max(created_at) AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') last_et FROM mi_lowcap_lane_signals;
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) FROM mi_lowcap_lane_signals WHERE created_at >= '2026-10-01 04:00+00' GROUP BY 1 ORDER BY 1;
