SET default_transaction_read_only = on;
\copy (SELECT * FROM mi_live_fill_counterfactuals ORDER BY 1) TO STDOUT WITH CSV HEADER
