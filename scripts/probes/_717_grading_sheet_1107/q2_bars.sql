SET default_transaction_read_only = on;
\echo == IAG 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'IAG' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == SIG 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SIG' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == VFC 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'VFC' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == PAYS 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PAYS' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == APPN 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'APPN' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == HAE 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'HAE' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == PAY 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PAY' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == FNKO 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'FNKO' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == PAR 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PAR' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == RSKD 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'RSKD' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == PLSE 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PLSE' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == BHC 2026-11-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'BHC' AND trade_date <= DATE '2026-11-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
