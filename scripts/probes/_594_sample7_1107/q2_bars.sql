SET default_transaction_read_only = on;
\echo == NX 2026-09-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'NX' AND trade_date <= DATE '2026-09-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == AFYA 2026-10-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'AFYA' AND trade_date <= DATE '2026-10-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == PLAB 2026-08-26
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PLAB' AND trade_date <= DATE '2026-08-26' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == SNOW 2026-09-03
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SNOW' AND trade_date <= DATE '2026-09-03' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == MGNI 2026-08-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'MGNI' AND trade_date <= DATE '2026-08-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == AMLX 2026-08-18
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'AMLX' AND trade_date <= DATE '2026-08-18' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == SAIC 2026-08-31
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SAIC' AND trade_date <= DATE '2026-08-31' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == MED 2026-08-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'MED' AND trade_date <= DATE '2026-08-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == CODI 2026-08-11
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'CODI' AND trade_date <= DATE '2026-08-11' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == KODK 2026-08-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'KODK' AND trade_date <= DATE '2026-08-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == BIRK 2026-08-13
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'BIRK' AND trade_date <= DATE '2026-08-13' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == BULL 2026-08-20
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'BULL' AND trade_date <= DATE '2026-08-20' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
