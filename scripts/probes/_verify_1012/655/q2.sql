\echo == mi_themes columns
select column_name, data_type from information_schema.columns where table_name='mi_themes' order by ordinal_position;
