-- Run AFTER ~17:15 ET Mon 2026-10-12 (14:15 PT). Read-only. Heartbeat + every verdict row of tonight's pass, with the child's discovery source.
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text ts, event_type, summary, detail
FROM mi_audit_log
WHERE event_type LIKE 'theme_parent_pass%'
  AND created_at > '2026-10-12 17:00:00-04'
ORDER BY id;
