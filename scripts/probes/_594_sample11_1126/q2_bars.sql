SET default_transaction_read_only = on;
\echo == HRI 2026-10-27
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'HRI' AND trade_date <= DATE '2026-10-27' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == DAKT 2026-09-02
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'DAKT' AND trade_date <= DATE '2026-09-02' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == FIGS 2026-08-07
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'FIGS' AND trade_date <= DATE '2026-08-07' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == AXGN 2026-10-28
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'AXGN' AND trade_date <= DATE '2026-10-28' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == ZBRA 2026-08-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ZBRA' AND trade_date <= DATE '2026-08-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == TBI 2026-08-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'TBI' AND trade_date <= DATE '2026-08-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == PAYC 2026-08-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PAYC' AND trade_date <= DATE '2026-08-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == TSAT 2026-08-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'TSAT' AND trade_date <= DATE '2026-08-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == SOLS 2026-08-28
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SOLS' AND trade_date <= DATE '2026-08-28' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == WEN 2026-10-28
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'WEN' AND trade_date <= DATE '2026-10-28' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == MFIC 2026-10-27
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'MFIC' AND trade_date <= DATE '2026-10-27' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == IRON 2026-10-19
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'IRON' AND trade_date <= DATE '2026-10-19' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
