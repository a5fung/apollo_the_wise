-- #685 follow-up read (one SELECT set): why did live NOT sell OKTA at the 09-11 close when SMA10 (168.78) > close (166.50)?
\echo === OKTA_0911 ===
SELECT id, created_at AT TIME ZONE 'America/New_York' AS created_et, event_type, left(summary, 400) AS summary, left(detail, 900) AS detail
FROM mi_audit_log WHERE created_at >= '2026-09-10 16:00' AND created_at < '2026-09-15 10:00'
  AND (summary ILIKE '%OKTA%' OR detail ILIKE '%OKTA%' OR event_type ILIKE '%exit%' OR event_type ILIKE '%position%' OR event_type ILIKE '%eod%' OR event_type ILIKE '%job%')
ORDER BY created_at;
\echo === SEI_0911 ===
SELECT id, created_at AT TIME ZONE 'America/New_York' AS created_et, event_type, left(summary, 300) AS summary
FROM mi_audit_log WHERE created_at >= '2026-09-08' AND created_at < '2026-09-15' AND (summary ILIKE '%SEI%' OR detail ILIKE '%"SEI"%') AND event_type NOT ILIKE 'stop_refresh_ran'
ORDER BY created_at;
\echo === OKTA_ALL_EXIT_EVENTS ===
SELECT id, created_at AT TIME ZONE 'America/New_York' AS created_et, event_type, left(summary, 300) AS summary
FROM mi_audit_log WHERE created_at >= '2026-08-27' AND (summary ILIKE '%OKTA%') AND (event_type ILIKE '%exit%' OR event_type ILIKE '%sma%' OR event_type ILIKE '%trail%' OR event_type ILIKE '%close%')
ORDER BY created_at;
