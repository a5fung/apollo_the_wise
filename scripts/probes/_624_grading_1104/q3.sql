SET default_transaction_read_only = on;
SELECT to_char(scan_date,'YYYY-MM') m, count(*) AS signals, count(DISTINCT (ticker, scan_date)) AS ticker_days FROM mi_lowcap_lane_signals GROUP BY 1 ORDER BY 1;
SELECT count(*) FROM mi_lowcap_lane_signals WHERE scan_date >= '2026-10-12';
\dt mi_lowcap*
