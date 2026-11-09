SET default_transaction_read_only = on;
SELECT ticker, list_rank, round(level::numeric,2) level, round(order_score::numeric,3) score, round(adr20::numeric*100,2) adr_pct FROM mi_breakout_v1_list WHERE scan_date = DATE '2026-11-05' ORDER BY list_rank;
