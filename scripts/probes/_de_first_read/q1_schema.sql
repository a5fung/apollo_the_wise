SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_delayed_entry_trigger' ORDER BY ordinal_position;
SELECT CURRENT_DATE, now() AT TIME ZONE 'America/New_York';
SELECT COUNT(*) FROM mi_delayed_entry_trigger WHERE realized_r IS NOT NULL AND fire_date >= DATE '2026-08-31' AND fire_date <= CURRENT_DATE - 30;
