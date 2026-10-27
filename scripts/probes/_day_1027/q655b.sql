SET default_transaction_read_only = on;
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_validation_cooldowns';
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York')::time, max(created_at AT TIME ZONE 'America/New_York')::time FROM mi_audit_log
 WHERE created_at BETWEEN '2026-10-26 16:30-04' AND '2026-10-26 20:00-04' AND (event_type ILIKE '%valid%' OR event_type ILIKE '%descr%') GROUP BY 1 ORDER BY 1;
SELECT created_at AT TIME ZONE 'America/New_York' et, left(summary,250) FROM mi_audit_log WHERE created_at BETWEEN '2026-10-26 16:30-04' AND '2026-10-26 20:00-04' AND event_type ILIKE '%validation%' ORDER BY id LIMIT 4;
