SET default_transaction_read_only = on;
SELECT scan_date, count(*) FROM mi_breakout_v1_list WHERE scan_date >= '2026-11-09' GROUP BY 1 ORDER BY 1;
\d mi_breakout_v1_list
