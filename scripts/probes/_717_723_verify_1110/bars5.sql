SET default_transaction_read_only = on;
\echo == ABCL 2026-11-09
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ABCL' AND trade_date <= DATE '2026-11-09' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == MRNA 2026-11-09
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'MRNA' AND trade_date <= DATE '2026-11-09' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == NVAX 2026-11-09
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'NVAX' AND trade_date <= DATE '2026-11-09' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == OUST 2026-11-09
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'OUST' AND trade_date <= DATE '2026-11-09' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == SPCE 2026-11-09
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SPCE' AND trade_date <= DATE '2026-11-09' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
