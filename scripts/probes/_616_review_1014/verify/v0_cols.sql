\pset pager off
\echo == all columns of mi_delayed_entry_trigger
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_delayed_entry_trigger' ORDER BY ordinal_position;
\echo == all columns of voided table (names only)
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_delayed_entry_trigger_voided_0901';
\echo == now
SELECT now(), now() AT TIME ZONE 'America/New_York' AS now_et;
