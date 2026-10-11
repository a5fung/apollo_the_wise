\echo == mi_audit_log columns
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_audit_log';

\echo == rows mentioning too_small (any column)
SELECT count(*) AS rows_mentioning_too_small FROM mi_audit_log
WHERE event_type ILIKE '%too_small%' OR detail::text ILIKE '%too_small%' OR summary ILIKE '%too_small%';

\echo == profit_trigger / partial rows since era D (2026-09-06), per event
SELECT event_type, count(*) AS n, min(created_at)::date AS first, max(created_at)::date AS last
FROM mi_audit_log
WHERE created_at >= '2026-09-06' AND event_type IN ('profit_trigger_fired','profit_trigger_failed','partial_exit_started','partial_exit_committed','partial_exit_aborted','partial_exit_paused')
GROUP BY 1 ORDER BY 1;

\echo == era-D profit_trigger_fired rows
SELECT created_at, event_type, summary, detail FROM mi_audit_log
WHERE created_at >= '2026-09-06' AND event_type IN ('profit_trigger_fired','profit_trigger_failed')
ORDER BY created_at LIMIT 40;

\echo == era-D partial_exit_committed rows
SELECT created_at, event_type, summary FROM mi_audit_log
WHERE created_at >= '2026-09-06' AND event_type = 'partial_exit_committed' ORDER BY created_at;
