SET default_transaction_read_only = on;
\echo == the list row (scan 10-30) with every gate value
SELECT scan_date, ticker, level, round(adr20::numeric,4) adr20, rs_best, close, gates::text FROM mi_breakout_v1_list WHERE ticker = 'MTW' ORDER BY scan_date DESC LIMIT 3;
\echo == daily bars since 2026-07-01
\copy (SELECT trade_date, open_price, high_price, low_price, close_price, volume FROM mi_daily_closes WHERE ticker = 'MTW' AND trade_date >= '2026-07-01' ORDER BY trade_date) TO STDOUT WITH CSV HEADER
