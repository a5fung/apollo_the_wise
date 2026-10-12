SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary,260) s FROM mi_audit_log
WHERE event_type='llm_request_rewrite_adopted' AND created_at >= '2026-10-09' ORDER BY created_at;
