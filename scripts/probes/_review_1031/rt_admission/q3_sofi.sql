SET default_transaction_read_only = on;
SELECT to_char(created_at AT TIME ZONE 'America/New_York', 'HH24:MI:SS') AS t_et, event_type, left(replace(coalesce(summary,''), E'\n', ' '), 200) AS summary
FROM mi_audit_log WHERE (created_at AT TIME ZONE 'America/New_York')::date = '2026-10-27'
  AND (summary ILIKE '%SOFI%' OR detail ILIKE '%"SOFI"%') ORDER BY created_at LIMIT 40;
