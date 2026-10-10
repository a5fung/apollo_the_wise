-- #312 Step A fix round: column check for mi_live_trades. READ-ONLY.
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name='mi_live_trades' AND (column_name LIKE '%\_at' OR column_name LIKE '%date%' OR column_name IN ('status','account_mode','exit_reason','skip_reason'))
ORDER BY ordinal_position;
