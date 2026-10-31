SET default_transaction_read_only = on;
\echo == renaming merged rows: validated_against equals merged_name?
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_date,
       substring(detail from 'merged_name=''([^'']*)''') AS merged_name,
       substring(detail from 'validated_against=''([^'']*)''') AS validated_against
FROM mi_audit_log WHERE event_type = 'theme_thesis_merged' AND created_at >= '2026-10-17' AND detail LIKE '%description_stored=%' ORDER BY created_at;
\echo == strips on renaming-merge nights: audit event types between proposed and merged that name a theme, 10-19 sample
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at >= '2026-10-17' AND event_type ILIKE '%strip%' GROUP BY 1 ORDER BY 2 DESC LIMIT 8;
