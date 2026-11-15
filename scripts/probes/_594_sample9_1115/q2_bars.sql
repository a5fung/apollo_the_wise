SET default_transaction_read_only = on;
\echo == TVTX 2026-08-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'TVTX' AND trade_date <= DATE '2026-08-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == SMWB 2026-08-12
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SMWB' AND trade_date <= DATE '2026-08-12' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == CRWV 2026-08-12
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'CRWV' AND trade_date <= DATE '2026-08-12' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == UMAC 2026-08-14
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'UMAC' AND trade_date <= DATE '2026-08-14' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == ACN 2026-10-01
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ACN' AND trade_date <= DATE '2026-10-01' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == SWIM 2026-08-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SWIM' AND trade_date <= DATE '2026-08-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == INTR 2026-10-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'INTR' AND trade_date <= DATE '2026-10-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == ANF 2026-08-26
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ANF' AND trade_date <= DATE '2026-08-26' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == WOLF 2026-10-08
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'WOLF' AND trade_date <= DATE '2026-10-08' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == CART 2026-08-07
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'CART' AND trade_date <= DATE '2026-08-07' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == SGMT 2026-09-30
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SGMT' AND trade_date <= DATE '2026-09-30' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == TATT 2026-08-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'TATT' AND trade_date <= DATE '2026-08-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
