SET default_transaction_read_only = on;
\echo == his promotions
SELECT created_at AT TIME ZONE 'America/New_York' AS et, left(detail, 300) FROM mi_audit_log WHERE event_type = 'theme_operator_promoted' AND created_at >= '2026-10-17' ORDER BY created_at;
\echo == Pass 1.5 absorptions and skips since 10-21
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(detail, 260) FROM mi_audit_log WHERE event_type IN ('theme_pass1_5_absorption','theme_pass1_5_skip') AND created_at >= '2026-10-21' ORDER BY created_at;
