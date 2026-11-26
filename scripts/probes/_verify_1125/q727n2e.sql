SET default_transaction_read_only = on;
SELECT theme_date, stage, round(score::numeric,1), tickers, source FROM mi_themes WHERE name ILIKE 'Bitcoin Miners%' ORDER BY theme_date DESC, created_at DESC LIMIT 6;
