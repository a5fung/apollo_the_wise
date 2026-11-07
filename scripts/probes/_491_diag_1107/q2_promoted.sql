SET default_transaction_read_only = on;
-- nightly promoted counts before and after the U2 deploy (10-23 evening)
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS night, event_type, detail::text AS detail
FROM mi_audit_log WHERE event_type IN ('shadow_themes_promoted','shadow_promotion_failed')
  AND created_at > TIMESTAMPTZ '2026-10-05 00:00+00' ORDER BY created_at;
