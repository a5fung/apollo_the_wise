SET default_transaction_read_only = on;
-- nightly run rows since the last read (10-31)
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS night, left(summary, 160) AS summary
FROM mi_audit_log WHERE event_type = 'parabolic_short_shadow_run' AND created_at > TIMESTAMPTZ '2026-10-31 00:00-04' ORDER BY created_at;
-- shadow rows since 10-31 by kind
SELECT * FROM mi_parabolic_short_shadow WHERE created_at > TIMESTAMPTZ '2026-10-31 00:00-04' ORDER BY created_at LIMIT 40;
SELECT count(*) FILTER (WHERE event_type ILIKE '%parabolic%error%' OR event_type ILIKE '%parabolic%fail%') AS errors
FROM mi_audit_log WHERE created_at > TIMESTAMPTZ '2026-10-31 00:00-04';
