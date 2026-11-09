SET default_transaction_read_only = on;
\echo == EVH 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'EVH' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == BILL 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'BILL' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == AMPH 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'AMPH' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == ONT 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ONT' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == CHTR 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'CHTR' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == OSCR 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'OSCR' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == DUOL 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'DUOL' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == CVLT 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'CVLT' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == MANE 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'MANE' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == PLNT 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PLNT' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == ASO 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ASO' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == BLKB 2026-11-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'BLKB' AND trade_date <= DATE '2026-11-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
