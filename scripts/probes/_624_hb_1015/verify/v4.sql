\pset pager off
\echo === V4-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === V4-1 P15 silence 10-06..10-15: names on the scan log at the 09:30/09:31 ticks with gap>=15 and prev_close>=5, any stage, with their cap (NULL cap = unknown)
SELECT scan_date, ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') t_et, reject_stage, round(gap_pct::numeric,1) gap, round(prev_close::numeric,2) pc, round((market_cap/1e6)::numeric) mcap_m, round(vol_percentile::numeric,1) vp, left(filter_reason,70) fr FROM mi_ep_scan_log WHERE scan_date >= '2026-10-06' AND (scan_time_et AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '09:31' AND gap_pct >= 15 AND prev_close >= 5 ORDER BY scan_date, ticker, scan_time_et;
