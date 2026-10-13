\pset pager off
\echo == W1. every rewrite row 10-03..10-05 (is 10-05 really the first nightly with the between_tools rewrite?)
SELECT created_at AT TIME ZONE 'America/New_York' at_et, left(summary,90) s FROM mi_audit_log WHERE event_type='llm_request_rewrite_adopted' AND created_at >= '2026-10-03 00:00-04' AND created_at < '2026-10-06 00:00-04' ORDER BY created_at;
\echo == W2. thinking-off jobs api calls 10-03..10-04 (did a weekend run exercise them?)
SELECT created_at AT TIME ZONE 'America/New_York' at_et, caller, stop_reason, output_tokens FROM api_usage WHERE created_at >= '2026-10-03 10:40-04' AND created_at < '2026-10-05 00:00-04' AND caller IN ('theme_validation','narrative_theme_discovery','theme_synthesis','theme_parent_adjudication') ORDER BY created_at;
