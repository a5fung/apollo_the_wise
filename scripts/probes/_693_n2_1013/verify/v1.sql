\pset pager off
\echo == V1. theme_validation per ET day since 09-28 (re-derived): calls, stops, >25 tok, mean, window, models
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, to_char((created_at AT TIME ZONE 'America/New_York')::date,'Dy') dow,
  count(*) n, count(*) FILTER (WHERE stop_reason='end_turn') endt, count(*) FILTER (WHERE stop_reason='max_tokens') maxtok,
  count(*) FILTER (WHERE stop_reason IS NULL OR stop_reason NOT IN ('end_turn','max_tokens')) other_stop,
  count(*) FILTER (WHERE output_tokens>25) gt25, round(100.0*count(*) FILTER (WHERE output_tokens>25)/count(*),0) pct25,
  round(avg(output_tokens),1) mean, max(output_tokens) mx, string_agg(DISTINCT model, ',') models,
  to_char(min(created_at AT TIME ZONE 'America/New_York'),'HH24:MI') first_et, to_char(max(created_at AT TIME ZONE 'America/New_York'),'HH24:MI') last_et,
  round(sum(cost_usd)::numeric,3) cost
FROM api_usage WHERE caller='theme_validation' AND created_at >= '2026-09-28 00:00-04' GROUP BY 1 ORDER BY 1;
\echo == V2. removals (ticker_revalidated_out) per ET day with time window + count outside 16:30-19:30 ET
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) removals,
  to_char(min(created_at AT TIME ZONE 'America/New_York'),'HH24:MI') first_et, to_char(max(created_at AT TIME ZONE 'America/New_York'),'HH24:MI') last_et,
  count(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::time NOT BETWEEN '16:30' AND '19:30') outside_window
FROM mi_audit_log WHERE event_type='ticker_revalidated_out' AND created_at >= '2026-09-28 00:00-04' GROUP BY 1 ORDER BY 1;
\echo == V3. validator side events per ET day since 09-28 (parse/API errors, rate limits, shield, mass flag)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) FROM mi_audit_log
WHERE created_at >= '2026-09-28 00:00-04' AND event_type IN ('validation_error','validation_api_failure','validation_rate_limited','validation_removal_shielded','validation_mass_removal_name_suspect','anthropic_rate_limited')
GROUP BY 1,2 ORDER BY 1,2;
\echo == V4. tonight theme_validation calls outside the nightly window (population)
SELECT count(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::time NOT BETWEEN '16:55' AND '19:30') outside, count(*) total
FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13';
\echo == V5. any non-clean stop by the four jobs + validator since deploy 10-03 10:40 ET
SELECT caller, model, stop_reason, count(*) FROM api_usage WHERE created_at >= '2026-10-03 10:40-04'
 AND caller IN ('theme_validation','narrative_theme_discovery','theme_synthesis','theme_parent_adjudication')
GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo == V6. truncation / refusal / near-ceiling audit events since 10-03 (all callers)
SELECT created_at AT TIME ZONE 'America/New_York' at_et, event_type, left(summary,140) s FROM mi_audit_log
WHERE created_at >= '2026-10-03 00:00-04' AND (event_type ILIKE '%trunc%' OR event_type ILIKE '%refus%' OR event_type ILIKE '%ceiling%') ORDER BY created_at;
\echo == V7. four-job run events Tue 10-13 (error counts in summary)
SELECT created_at AT TIME ZONE 'America/New_York' at_et, event_type, left(summary,170) s FROM mi_audit_log
WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13' AND event_type IN ('theme_synthesis_run','theme_parent_pass_ran','narrative_theme_discovery_ran','llm_request_rewrite_adopted') ORDER BY created_at;
\echo == V8. container boots since 10-09 (era: which code ran tonight)
SELECT job_id, started_at AT TIME ZONE 'America/New_York' started_et FROM mi_job_runs WHERE job_id ILIKE '%boot%' AND started_at >= '2026-10-09 00:00-04' ORDER BY started_at;
\echo == V9. validation/nightly job runs 10-12 and 10-13
SELECT job_id, status, started_at AT TIME ZONE 'America/New_York' started_et, rows_written, left(coalesce(error_message,''),120) err FROM mi_job_runs
WHERE started_at >= '2026-10-12 16:30-04' AND job_id IN ('nightly_data_pull','theme_synthesis','post_nightly_audit') ORDER BY started_at;
