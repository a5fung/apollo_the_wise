SET default_transaction_read_only = on;
\echo == UFPT 2026-08-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'UFPT' AND trade_date <= DATE '2026-08-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == ELPC 2026-10-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ELPC' AND trade_date <= DATE '2026-10-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == INSM 2026-08-06
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'INSM' AND trade_date <= DATE '2026-08-06' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == TWLO 2026-08-07
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'TWLO' AND trade_date <= DATE '2026-08-07' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == CRMD 2026-08-13
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'CRMD' AND trade_date <= DATE '2026-08-13' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == SBS 2026-10-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'SBS' AND trade_date <= DATE '2026-10-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == ACHR 2026-08-10
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'ACHR' AND trade_date <= DATE '2026-08-10' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == PCVX 2026-10-05
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'PCVX' AND trade_date <= DATE '2026-10-05' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == W 2026-08-04
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'W' AND trade_date <= DATE '2026-08-04' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == AMPX 2026-09-28
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'AMPX' AND trade_date <= DATE '2026-09-28' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == INNV 2026-09-09
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'INNV' AND trade_date <= DATE '2026-09-09' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
\echo == HELE 2026-10-08
SELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = 'HELE' AND trade_date <= DATE '2026-10-08' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;
