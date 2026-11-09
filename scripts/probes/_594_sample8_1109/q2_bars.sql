SET default_transaction_read_only = on;
\echo == FLR 2026-08-07
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'FLR' AND trade_date <= DATE '2026-08-07' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == ATRO 2026-08-12
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ATRO' AND trade_date <= DATE '2026-08-12' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == WPP 2026-08-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'WPP' AND trade_date <= DATE '2026-08-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == CRK 2026-09-01
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'CRK' AND trade_date <= DATE '2026-09-01' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == SITM 2026-08-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SITM' AND trade_date <= DATE '2026-08-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == YEXT 2026-09-01
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'YEXT' AND trade_date <= DATE '2026-09-01' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == WOR 2026-09-23
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'WOR' AND trade_date <= DATE '2026-09-23' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == AMRC 2026-08-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'AMRC' AND trade_date <= DATE '2026-08-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == EFXT 2026-10-01
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'EFXT' AND trade_date <= DATE '2026-10-01' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == PICS 2026-10-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PICS' AND trade_date <= DATE '2026-10-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == VOYG 2026-08-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'VOYG' AND trade_date <= DATE '2026-08-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == CNH 2026-08-03
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'CNH' AND trade_date <= DATE '2026-08-03' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
