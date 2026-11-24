SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York', event_type, left(summary,220) FROM mi_audit_log WHERE created_at BETWEEN '2026-11-24 17:03:00-05' AND '2026-11-24 17:05:00-05' ORDER BY created_at;
SELECT detail::text FROM mi_audit_log WHERE event_type='theme_merge_pairs_proposed' AND created_at >= '2026-11-24 00:00-05';
