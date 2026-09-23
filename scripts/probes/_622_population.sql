SELECT scan_date, ticker, MAX(gap_pct) AS max_gap, MIN(prev_close) AS prev_close
FROM mi_ep_scan_log
WHERE filter_reason LIKE '%mcap_too_small%' AND scan_date >= CURRENT_DATE - 90
GROUP BY scan_date, ticker ORDER BY scan_date, ticker;
