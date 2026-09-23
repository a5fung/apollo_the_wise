SELECT 'census' AS q, count(*)::text AS a, min(trade_date)::text AS b, max(trade_date)::text AS c FROM mi_pivot_stop_shadow;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_pivot_stop_shadow' ORDER BY ordinal_position;
