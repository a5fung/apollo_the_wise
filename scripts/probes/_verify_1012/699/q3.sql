select column_name from information_schema.columns where table_name='mi_live_trades' order by ordinal_position;
\echo ===
select column_name from information_schema.columns where table_name='mi_ep_alerts' order by ordinal_position;
