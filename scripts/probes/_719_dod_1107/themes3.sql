SET default_transaction_read_only = on;
WITH s AS (SELECT DISTINCT trade_date FROM mi_daily_closes WHERE trade_date <= DATE '2026-11-06' AND trade_date >= DATE '2026-09-20' ORDER BY 1 DESC LIMIT 22)
SELECT 'S', trade_date, NULL, NULL FROM s;
SELECT 'C', ticker, trade_date, close FROM mi_daily_closes WHERE ticker = ANY(ARRAY['FIVN','INFQ','IONQ','LYFT','RGTI','RNG','VIA','YMM']) AND trade_date >= DATE '2025-12-20' AND trade_date <= DATE '2026-11-06' ORDER BY 2,3;
