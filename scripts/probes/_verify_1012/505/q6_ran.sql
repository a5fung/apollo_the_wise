SELECT id,(created_at AT TIME ZONE 'America/New_York')::text ts, summary FROM mi_audit_log WHERE event_type='theme_parent_pass_ran' AND created_at > '2026-09-26' ORDER BY id;
