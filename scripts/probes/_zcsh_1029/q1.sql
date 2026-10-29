SET default_transaction_read_only = on;
\echo == bars
SELECT trade_date, open_price, high_price, low_price, close, volume FROM mi_daily_closes WHERE ticker='ZCSH' AND trade_date >= '2026-03-01' ORDER BY trade_date;
\echo == security type
SELECT * FROM mi_security_types WHERE ticker='ZCSH';
\echo == breakout shadow watch rows
SELECT watch_date, left(features::text, 300) FROM mi_consolidation_breakout_watch WHERE ticker='ZCSH' ORDER BY watch_date DESC LIMIT 5;
\echo == coil board
SELECT * FROM mi_anticipation_candidates WHERE ticker='ZCSH' ORDER BY 1 DESC LIMIT 3;
