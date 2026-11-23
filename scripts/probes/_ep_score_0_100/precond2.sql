SET default_transaction_read_only = on;
SELECT (score_side IS NULL) AS no_side, (ep_score IS NOT NULL) AS scored, min(scan_date), max(scan_date), count(*)
FROM mi_ep_scan_log WHERE scan_date >= '2026-08-22' GROUP BY 1,2 ORDER BY 1,2;
