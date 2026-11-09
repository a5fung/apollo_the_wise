SET default_transaction_read_only = on;
SELECT ticker, trade_date, close FROM mi_daily_closes WHERE ticker = ANY(ARRAY['ARIS','RYZ']) AND trade_date BETWEEN DATE '2025-12-15' AND DATE '2026-01-10' ORDER BY 1,2;
