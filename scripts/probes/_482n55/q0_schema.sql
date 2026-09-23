SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('mi_orb_shadow_trades','mi_live_trades','mi_daily_closes','mi_strategies')
ORDER BY table_name, ordinal_position;
