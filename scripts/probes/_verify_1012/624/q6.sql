\echo === shadow lane signals
SELECT count(*) n, count(DISTINCT scan_date) sessions, min(scan_date) first, max(scan_date) last FROM mi_lowcap_lane_signals;
\echo === shadow lane signals last 5
SELECT scan_date, ticker FROM mi_lowcap_lane_signals ORDER BY scan_date DESC, ticker LIMIT 5;
\echo === lane replays (shadow) count by status
SELECT status, count(*) FROM mi_lowcap_lane_replays GROUP BY 1 ORDER BY 2 DESC;
