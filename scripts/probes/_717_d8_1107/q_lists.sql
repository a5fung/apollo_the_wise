SET default_transaction_read_only = on;
SELECT scan_date, string_agg(ticker, ',' ORDER BY list_rank) FROM mi_breakout_v1_list
 WHERE scan_date IN ('2026-11-05','2026-11-06') GROUP BY 1 ORDER BY 1;
