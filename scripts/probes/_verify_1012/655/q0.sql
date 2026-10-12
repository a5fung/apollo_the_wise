\echo == mi_audit_log columns
select column_name, data_type from information_schema.columns where table_name='mi_audit_log' order by ordinal_position;
\echo == safeguard states for theme
select * from mi_safeguard_state where key ilike '%theme%' or name ilike '%theme%' limit 0;
