\echo == which events mention too_small
SELECT event_type, count(*) AS n, min(created_at)::date AS first, max(created_at)::date AS last,
       count(*) FILTER (WHERE detail::text ILIKE '%too_small_to_split%' OR summary ILIKE '%too_small_to_split%') AS exact_split_skip
FROM mi_audit_log
WHERE event_type ILIKE '%too_small%' OR detail::text ILIKE '%too_small%' OR summary ILIKE '%too_small%'
GROUP BY 1 ORDER BY 2 DESC;

\echo == sample of one
SELECT created_at, event_type, left(summary, 160) AS summary FROM mi_audit_log
WHERE detail::text ILIKE '%too_small%' OR summary ILIKE '%too_small%' ORDER BY created_at DESC LIMIT 3;

\echo == era-D profit_trigger_failed + partial_exit_aborted/started rows
SELECT created_at, event_type, left(summary, 200) AS summary FROM mi_audit_log
WHERE created_at >= '2026-09-06' AND event_type IN ('partial_exit_aborted','partial_exit_started') ORDER BY created_at;
