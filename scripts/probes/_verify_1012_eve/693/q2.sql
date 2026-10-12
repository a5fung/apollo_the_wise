\echo == removals detail
SELECT created_at AT TIME ZONE 'America/New_York' at_et, summary, left(detail::text,400) det FROM mi_audit_log WHERE event_type='ticker_revalidated_out' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' ORDER BY created_at;
\echo == rewrite adopted rows
SELECT created_at AT TIME ZONE 'America/New_York' at_et, summary, left(detail::text,500) det FROM mi_audit_log WHERE event_type='llm_request_rewrite_adopted' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' ORDER BY created_at;
\echo == cooldown triggered
SELECT created_at AT TIME ZONE 'America/New_York' at_et, summary FROM mi_audit_log WHERE event_type='validation_cooldown_triggered' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' ORDER BY created_at;
\echo == any error/truncation/refusal events 10-12 17:00-18:30 ET
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at >= '2026-10-12 17:00-04' AND created_at < '2026-10-12 18:30-04' AND (event_type ILIKE '%error%' OR event_type ILIKE '%fail%' OR event_type ILIKE '%trunc%' OR event_type ILIKE '%refus%') GROUP BY 1;
\echo == other callers truncated/max_tokens tonight
SELECT caller, stop_reason, count(*) FROM api_usage WHERE created_at >= '2026-10-12 17:00-04' AND created_at < '2026-10-12 18:30-04' GROUP BY 1,2 ORDER BY 1,2;
