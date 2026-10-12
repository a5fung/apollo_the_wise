\echo == mi_safeguard_state columns
select column_name from information_schema.columns where table_name='mi_safeguard_state' order by ordinal_position;
