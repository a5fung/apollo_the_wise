\pset pager off
\pset format aligned
\echo == H. per-day theme_validation history (calls, gt25, mean, max_tok, removals)
WITH c AS (
  SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n, count(*) FILTER (WHERE output_tokens>25) gt25,
         round(avg(output_tokens),1) mean, count(*) FILTER (WHERE stop_reason='max_tokens') max_tok, count(*) FILTER (WHERE stop_reason<>'end_turn') non_end
  FROM api_usage WHERE caller='theme_validation' AND created_at > '2026-09-26' GROUP BY 1),
r AS (
  SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) removals FROM mi_audit_log WHERE event_type='ticker_revalidated_out' AND created_at > '2026-09-26' GROUP BY 1)
SELECT c.d, to_char(c.d,'Dy') dow, c.n, c.gt25, c.mean, c.max_tok, c.non_end, coalesce(r.removals,0) removals FROM c LEFT JOIN r USING (d) ORDER BY c.d;
\echo == I. the four job run events + cooldown, detail Tue 10-13
SELECT created_at AT TIME ZONE 'America/New_York' at_et, event_type, left(summary,200) summ, left(detail::text,700) det FROM mi_audit_log
WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13' AND event_type IN ('theme_synthesis_run','theme_parent_pass_ran','narrative_theme_discovery_ran','validation_cooldown_triggered') ORDER BY created_at;
\echo == J. theme-ish job runs Tue evening
SELECT job_id, status, started_at AT TIME ZONE 'America/New_York' started_et, duration_s, rows_written, left(coalesce(error_message,''),200) err
FROM mi_job_runs WHERE started_at >= '2026-10-13 16:30-04' AND (job_id ILIKE '%theme%' OR job_id ILIKE '%narrat%' OR job_id ILIKE '%synth%' OR job_id ILIKE '%valid%' OR job_id ILIKE '%nightly%' OR job_id ILIKE '%pull%' OR job_id ILIKE '%rs_%' OR job_id ILIKE '%ecosystem%' OR status<>'success') ORDER BY started_at;
\echo == K. non-success job runs since 10-13 16:00 ET (any job)
SELECT job_id, status, started_at AT TIME ZONE 'America/New_York' started_et, left(coalesce(error_message,''),200) err FROM mi_job_runs WHERE started_at >= '2026-10-13 16:00-04' AND status<>'success' ORDER BY started_at;
\echo == L. api_usage stop_reason x caller, non end_turn/tool_use, whole ET day Tue 10-13
SELECT caller, model, stop_reason, count(*) FROM api_usage WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13' AND stop_reason NOT IN ('end_turn','tool_use') GROUP BY 1,2,3 ORDER BY 1;
\echo == M. error/fail/refusal/truncation audit events Tue 10-13 excluding fmp
SELECT event_type, count(*), min(left(summary,160)) sample FROM mi_audit_log WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13'
 AND (event_type ILIKE '%error%' OR event_type ILIKE '%fail%' OR event_type ILIKE '%refus%' OR event_type ILIKE '%trunc%' OR event_type ILIKE '%ceiling%' OR event_type ILIKE '%parse%') AND event_type<>'api_failure_fmp' GROUP BY 1 ORDER BY 1;
\echo == N. rewrite adopted: which caller/summary at 17:06 Tue and 17:10 Mon, full detail
SELECT created_at AT TIME ZONE 'America/New_York' at_et, summary, detail::text det FROM mi_audit_log WHERE event_type='llm_request_rewrite_adopted' AND created_at >= '2026-10-12 17:00-04' AND summary ILIKE '%between_tools%' ORDER BY created_at;
\echo == O. theme_validation per-call output tokens distribution Tue 10-13
SELECT output_tokens, stop_reason, round(cost_usd::numeric,4) cost FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13' ORDER BY created_at;
