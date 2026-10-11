SELECT 'mi_strategies' AS t, string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_strategies'
UNION ALL
SELECT 'mi_live_trades', string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_live_trades';
