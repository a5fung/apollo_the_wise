SET default_transaction_read_only = on;
SELECT column_name FROM information_schema.columns WHERE table_name = 'mi_metric_baselines' ORDER BY ordinal_position;
