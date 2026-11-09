SET default_transaction_read_only = on;
SELECT ticker, min(trade_date) AS first_bar, max(trade_date) FILTER (WHERE trade_date <= DATE '2025-12-31') AS last_bar_by_ye, count(*) AS bars
FROM mi_daily_closes WHERE ticker IN ('ARIS','RYZ') GROUP BY 1;
