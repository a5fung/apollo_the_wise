-- every flag_digest_sent / error row since the row type shipped (#697 1b 10-11)
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, summary, LEFT(detail,700) AS detail
FROM mi_audit_log
WHERE event_type IN ('flag_digest_sent','flag_digest_sent_error')
  AND created_at >= '2026-10-03'
ORDER BY created_at;
