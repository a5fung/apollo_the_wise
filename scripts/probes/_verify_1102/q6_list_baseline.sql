SET default_transaction_read_only = on;
SELECT scan_date, ticker, list_rank, round(adr20::numeric,4) AS adr20 FROM mi_breakout_v1_list WHERE scan_date = (SELECT MAX(scan_date) FROM mi_breakout_v1_list) ORDER BY adr20;
