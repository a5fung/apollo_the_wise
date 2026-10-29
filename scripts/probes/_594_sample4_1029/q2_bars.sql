SET default_transaction_read_only = on;
\echo == AKAM 2026-09-25
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'AKAM' AND trade_date < DATE '2026-09-25' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == PHVS 2026-09-08
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PHVS' AND trade_date < DATE '2026-09-08' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == DFTX 2026-09-14
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'DFTX' AND trade_date < DATE '2026-09-14' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == GNRC 2026-09-17
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'GNRC' AND trade_date < DATE '2026-09-17' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == ROIV 2026-09-08
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ROIV' AND trade_date < DATE '2026-09-08' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == CCL 2026-09-29
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'CCL' AND trade_date < DATE '2026-09-29' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == ODD 2026-09-09
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ODD' AND trade_date < DATE '2026-09-09' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
\echo == SIG 2026-09-09
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SIG' AND trade_date < DATE '2026-09-09' ORDER BY trade_date DESC LIMIT 160) x ORDER BY trade_date;
