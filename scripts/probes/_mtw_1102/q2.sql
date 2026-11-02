SET default_transaction_read_only = on;
\copy (SELECT * FROM mi_daily_closes WHERE ticker = 'MTW' AND trade_date >= '2026-06-15' ORDER BY trade_date) TO STDOUT WITH CSV HEADER
