SET default_transaction_read_only = on;
SELECT (created_at AT TIME ZONE 'America/New_York')::time(3) AS et, event_type, left(coalesce(summary, detail::text, ''), 260) AS s
FROM mi_audit_log WHERE created_at >= '2026-10-29 09:00-04' AND (coalesce(summary,'') ILIKE '%GKOS%' OR coalesce(detail::text,'') ILIKE '%GKOS%')
ORDER BY created_at LIMIT 60;
SELECT (created_at AT TIME ZONE 'America/New_York')::time(3) AS et, event_type, left(coalesce(summary, detail::text, ''), 200) AS s
FROM mi_audit_log WHERE created_at >= '2026-10-29 09:29-04' AND created_at < '2026-10-29 09:36-04'
  AND (event_type ILIKE '%bar_stream%' OR event_type ILIKE '%stream%' OR event_type ILIKE '%orb%') ORDER BY created_at LIMIT 40;
