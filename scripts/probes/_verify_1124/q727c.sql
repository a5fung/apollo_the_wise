SET default_transaction_read_only = on;
SELECT theme_date, name, stage, tickers, source FROM mi_themes WHERE name ILIKE 'Bitcoin Miners%' AND theme_date >= '2026-11-23' ORDER BY theme_date;
