SELECT 'daily_closes_min' k, MIN(trade_date)::text v FROM mi_daily_closes
UNION ALL SELECT 'daily_closes_max', MAX(trade_date)::text FROM mi_daily_closes
UNION ALL SELECT 'flag_min', MIN(scan_date)::text FROM mi_flag_candidates
UNION ALL SELECT 'flag_max', MAX(scan_date)::text FROM mi_flag_candidates
UNION ALL SELECT 'flag_distinct_days', COUNT(DISTINCT scan_date)::text FROM mi_flag_candidates
UNION ALL SELECT 'strategy_flag', (SELECT phase||'/'||enabled::text FROM mi_strategies WHERE strategy_id='flag_continuation')
UNION ALL SELECT 'strategy_cols', (SELECT string_agg(column_name,',') FROM information_schema.columns WHERE table_name='mi_strategies')
UNION ALL SELECT 'stock_scores_cols', (SELECT string_agg(column_name,',') FROM information_schema.columns WHERE table_name='mi_stock_scores')
UNION ALL SELECT 'audit_cols', (SELECT string_agg(column_name,',') FROM information_schema.columns WHERE table_name='mi_audit_log')
UNION ALL SELECT 'flag_breaks_cols', (SELECT string_agg(column_name,',') FROM information_schema.columns WHERE table_name='mi_flag_breaks')
UNION ALL SELECT 'flag_cand_cols', (SELECT string_agg(column_name,',') FROM information_schema.columns WHERE table_name='mi_flag_candidates')
UNION ALL SELECT 'job_tables', (SELECT string_agg(table_name,',') FROM information_schema.tables WHERE table_name LIKE '%job%')
;
