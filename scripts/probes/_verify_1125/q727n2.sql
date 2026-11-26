SET default_transaction_read_only = on;
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*), left(string_agg(summary,' || '),400)
FROM mi_audit_log WHERE created_at > now() - interval '3 days'
 AND (event_type LIKE 'theme_member_pruned%' OR event_type LIKE 'theme_pass1_5%' OR event_type LIKE 'theme_sector_filter%')
GROUP BY 1,2 ORDER BY 1,2;
SELECT run_date, stage, members FROM mi_themes WHERE name ILIKE 'Bitcoin Miners%' ORDER BY run_date DESC LIMIT 3;
