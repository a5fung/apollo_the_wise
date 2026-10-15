\pset pager off
\echo === V5-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === V5-1 P15 lane audit rows since 10-06 ET (cap unreadable / tick cap / any lowcap_lane_* except replay)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-10-06 04:00+00' AND event_type LIKE 'lowcap_lane%' AND event_type <> 'lowcap_lane_replay_recorded' ORDER BY id;
\echo === V5-2 GRML/AEHL prior P15 rows (cap on record)
SELECT ticker, scan_date, round((market_cap/1e6)::numeric) mcap_m, round(vol_percentile::numeric,1) vp, round(gap_pct::numeric,1) gap FROM mi_lowcap_lane_signals WHERE ticker IN ('GRML','AEHL','WFF','MMEDV','AIFA','COE') ORDER BY scan_date;
\echo === V5-3 any scan-log market cap ever recorded for the 10-06..10-14 gap>=15 unknown-cap names
SELECT ticker, max(scan_date) last_d, round((max(market_cap)/1e6)::numeric) mcap_m FROM mi_ep_scan_log WHERE ticker IN ('GRML','AEHL','WFF','MMEDV','AIFA','COE') AND market_cap IS NOT NULL GROUP BY 1 ORDER BY 1;
