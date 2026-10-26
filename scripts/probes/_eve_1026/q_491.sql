SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York' et, detail::jsonb->>'ticker' tk, detail::jsonb->>'from' frm, detail::jsonb->>'to' too
FROM mi_audit_log WHERE event_type='theme_member_rehomed' AND detail::jsonb->>'ticker' IN ('SHOE','ROL') ORDER BY id;
SELECT created_at AT TIME ZONE 'America/New_York' et, left(detail,700) FROM mi_audit_log WHERE event_type='theme_rehome_pass_ran' AND created_at >= '2026-10-26 12:00-04';
