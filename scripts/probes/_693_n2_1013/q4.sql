\pset pager off
\echo == U. the 10-08 truncation events in full
SELECT created_at AT TIME ZONE 'America/New_York' at_et, event_type, summary, left(detail::text,900) det FROM mi_audit_log WHERE event_type IN ('llm_truncation_live','llm_truncation_check','judge_verdict_truncated') AND created_at >= '2026-10-03' ORDER BY created_at;
\echo == V. any max_tokens stop in api_usage since 10-03 by caller
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, caller, model, count(*) FROM api_usage WHERE created_at >= '2026-10-03' AND stop_reason='max_tokens' GROUP BY 1,2,3 ORDER BY 1,2;
