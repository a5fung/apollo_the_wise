SET default_transaction_read_only = on;
\echo == LIFE 2026-08-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'LIFE' AND trade_date < DATE '2026-08-04' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == KOD 2026-09-28
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'KOD' AND trade_date < DATE '2026-09-28' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == EIKN 2026-08-19
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'EIKN' AND trade_date < DATE '2026-08-19' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == DCTH 2026-08-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'DCTH' AND trade_date < DATE '2026-08-06' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == NUAI 2026-09-21
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'NUAI' AND trade_date < DATE '2026-09-21' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == AESI 2026-09-25
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'AESI' AND trade_date < DATE '2026-09-25' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == ABCL 2026-08-10
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ABCL' AND trade_date < DATE '2026-08-10' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == ASPN 2026-08-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ASPN' AND trade_date < DATE '2026-08-06' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
