SET default_transaction_read_only = on;
SELECT id, created_at AT TIME ZONE 'America/New_York' et, left(summary,200) FROM mi_audit_log
WHERE event_type='magna53_open_floor_checked' AND created_at < TIMESTAMPTZ '2026-11-03 15:05:28+00' ORDER BY id LIMIT 10;
SELECT count(*) FILTER (WHERE detail ILIKE '%"mode": "shadow"%' AND detail ILIKE '%"verdict": "would_skip"%') shadow_would_skip,
       count(*) FILTER (WHERE detail ILIKE '%"mode": "shadow"%') shadow_rows
FROM mi_audit_log WHERE event_type='magna53_open_floor_checked' AND created_at < TIMESTAMPTZ '2026-11-03 15:05:28+00';
