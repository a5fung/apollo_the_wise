\pset pager off
\echo === now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === cols lane tables
SELECT table_name, string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name IN ('mi_lowcap_lane_signals','mi_lowcap_lane_replays','mi_lowcap_paper_lane_alerts','mi_lowcap_paper_lane_replays') GROUP BY 1;
