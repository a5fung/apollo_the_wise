SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, substring(detail from 'description_stored=(True|False)') AS stored,
       substring(detail from '(merged_name=''[^'']*''|new_name=''[^'']*''|winner=''[^'']*''|merged=''[^'']*'')') AS name_field,
       left(regexp_replace(detail, '^.*?(description_stored=)', '\1'), 400) AS tail
FROM mi_audit_log WHERE event_type = 'theme_thesis_merged' AND (created_at AT TIME ZONE 'America/New_York')::date = '2026-10-27';
