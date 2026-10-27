SET default_transaction_read_only = on;
SELECT id, created_at AT TIME ZONE 'America/New_York' et, left(summary,300), detail FROM mi_audit_log WHERE event_type IN ('mna_release_merit_grade','mna_release_without_merit_grade') AND created_at >= DATE '2026-10-03' ORDER BY id;
