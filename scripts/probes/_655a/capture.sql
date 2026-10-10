-- #655(a) replay capture, READ-ONLY. 30 nights of the Pass-2 sector-cap audit rows.
BEGIN TRANSACTION READ ONLY;
COPY (
  SELECT json_build_object(
    'id', id,
    'et', to_char(created_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS'),
    'event_type', event_type,
    'summary', summary,
    'detail', detail)
  FROM mi_audit_log
  WHERE event_type IN ('theme_sector_cap_absorbed','theme_sector_cap_not_absorbed','theme_sector_cap_dropped')
    AND created_at >= (now() - interval '30 days')
  ORDER BY created_at
) TO STDOUT;
COMMIT;
