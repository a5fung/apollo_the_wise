SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS et, event_type, replace(replace(left(summary,260),E'\t',' '),E'\n',' ') AS summary, replace(replace(left(detail,1800),E'\t',' '),E'\n',' ') AS detail
FROM mi_audit_log
WHERE created_at >= '2026-10-03 00:00:00-04'
  AND (event_type LIKE 'mna%' OR event_type LIKE 'open_window%' OR event_type LIKE '%headline%' OR event_type LIKE '%deal_pin%' OR event_type LIKE 'alpaca%')
ORDER BY created_at;
