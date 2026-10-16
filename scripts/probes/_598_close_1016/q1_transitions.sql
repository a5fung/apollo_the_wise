-- #598 close 10-16: every flag_stage_transition / error row since the 10-03 deploy
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, summary, detail
FROM mi_audit_log
WHERE event_type IN ('flag_stage_transition','flag_stage_transition_error')
  AND created_at >= '2026-10-03'
ORDER BY created_at;
