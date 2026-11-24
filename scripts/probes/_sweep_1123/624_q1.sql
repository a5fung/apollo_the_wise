SET default_transaction_read_only = on;
SELECT count(*) signals, count(DISTINCT scan_date) sessions, min(scan_date), max(scan_date), count(DISTINCT ticker) tickers FROM mi_lowcap_lane_signals;
SELECT outcome, entry_status, count(*) n, count(*) FILTER (WHERE meets_3r) tail3r, round(sum(realized_r)::numeric,2) sum_r, count(DISTINCT ticker) tickers FROM mi_lowcap_lane_replays GROUP BY 1,2 ORDER BY 1,2;
SELECT count(*) FILTER (WHERE outcome='settled') settled, count(DISTINCT ticker) FILTER (WHERE outcome='settled') settled_tickers, count(*) FILTER (WHERE outcome='settled' AND meets_3r) tail FROM mi_lowcap_lane_replays;
