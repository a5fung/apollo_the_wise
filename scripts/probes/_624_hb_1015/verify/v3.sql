\pset pager off
\echo === V3-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === V3-1 P15 shadow recorder signals: total + last scan_date
SELECT count(*) total, max(scan_date) last_scan_date FROM mi_lowcap_lane_signals;
\echo === V3-2 P15 signals by scan_date since 10-01
SELECT scan_date, count(*), string_agg(ticker, ',') FROM mi_lowcap_lane_signals WHERE scan_date >= '2026-10-01' GROUP BY 1 ORDER BY 1;
