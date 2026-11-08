SET default_transaction_read_only = on;
-- #720 §3 selection (L3): his /bgrade grades and the list rows (level, rank, order score) behind every breakout paper trade.
\copy (SELECT scan_date, ticker, grade, note, graded_at FROM mi_breakout_v1_grades ORDER BY scan_date, ticker) TO STDOUT WITH CSV HEADER
