SET default_transaction_read_only = on;
\d mi_cot_index_weekly
SELECT * FROM mi_cot_index_weekly WHERE market ILIKE '%gas%' OR market ILIKE 'NG%' ORDER BY 1 DESC LIMIT 12;
