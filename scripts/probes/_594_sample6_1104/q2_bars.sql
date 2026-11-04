SET default_transaction_read_only = on;
\echo == IOT 2026-09-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'IOT' AND trade_date <= DATE '2026-09-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == NTRA 2026-08-07
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'NTRA' AND trade_date <= DATE '2026-08-07' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == PAGS 2026-10-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PAGS' AND trade_date <= DATE '2026-10-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == CDRE 2026-08-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'CDRE' AND trade_date <= DATE '2026-08-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == KMT 2026-08-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'KMT' AND trade_date <= DATE '2026-08-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == ONON 2026-09-22
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ONON' AND trade_date <= DATE '2026-09-22' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == BLMN 2026-08-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'BLMN' AND trade_date <= DATE '2026-08-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == RSKD 2026-08-12
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'RSKD' AND trade_date <= DATE '2026-08-12' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == WGS 2026-08-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'WGS' AND trade_date <= DATE '2026-08-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == NESR 2026-08-10
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'NESR' AND trade_date <= DATE '2026-08-10' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == DORM 2026-08-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'DORM' AND trade_date <= DATE '2026-08-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == HLIT 2026-08-13
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'HLIT' AND trade_date <= DATE '2026-08-13' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
