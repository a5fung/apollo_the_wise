\pset pager off
\echo == P. thinking_disabled_to_between_tools rows since deploy 10-03 (first nightly after deploy)
SELECT created_at AT TIME ZONE 'America/New_York' at_et, left(summary,100) summ FROM mi_audit_log WHERE event_type='llm_request_rewrite_adopted' AND summary ILIKE '%between_tools%' AND created_at >= '2026-10-03' ORDER BY created_at;
\echo == Q. four-job run events 10-05..10-13 with error counts
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, left(summary,150) summ FROM mi_audit_log WHERE created_at >= '2026-10-05' AND event_type IN ('theme_synthesis_run','theme_parent_pass_ran','narrative_theme_discovery_ran') ORDER BY created_at;
\echo == R. any refusal / truncation / llm_* alarm events since deploy 10-03
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York') first_et, max(created_at AT TIME ZONE 'America/New_York') last_et FROM mi_audit_log WHERE created_at >= '2026-10-03' AND (event_type ILIKE '%refus%' OR event_type ILIKE '%trunc%' OR event_type ILIKE 'llm_%') GROUP BY 1 ORDER BY 1;
\echo == S. full synthesis_run detail Tue 10-13 (error keys?)
SELECT left(detail::text,1500) det FROM mi_audit_log WHERE event_type='theme_synthesis_run' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13';
\echo == T. thinking-off jobs token means since 10-05 (theme_parent_adjudication, theme_synthesis, narrative_theme_discovery)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, caller, count(*) n, round(avg(output_tokens),0) mean_out, count(*) FILTER (WHERE stop_reason NOT IN ('tool_use','end_turn')) bad_stop
FROM api_usage WHERE created_at >= '2026-10-03' AND caller IN ('theme_parent_adjudication','theme_synthesis','narrative_theme_discovery') GROUP BY 1,2 ORDER BY 2,1;
