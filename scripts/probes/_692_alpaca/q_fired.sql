SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI') AS hhmm, event_type,
  regexp_replace(summary, '[\r\n|]+', ' ', 'g') AS summary,
  regexp_replace(coalesce(detail::text,''), '[\r\n|]+', ' ', 'g') AS detail
FROM mi_audit_log
WHERE event_type IN ('mna_filter_fired','mna_filter_released','mna_headline_unanswered')
  AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-05-14' AND '2026-10-10'
ORDER BY created_at;
