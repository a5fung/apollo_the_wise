SET default_transaction_read_only = on;
\copy (SELECT l.scan_date, l.ticker, l.level, l.vol_bar, l.adr20, l.rs_best, l.close, l.list_rank, l.order_score FROM mi_breakout_v1_list l WHERE l.scan_date >= DATE '2026-10-29' ORDER BY l.scan_date, l.list_rank) TO STDOUT WITH CSV HEADER
