SET default_transaction_read_only = on;
SELECT trade_date, close FROM mi_daily_closes WHERE ticker='ARIS' AND trade_date IN (DATE '2025-10-14', DATE '2026-11-06');
