\pset pager off
\echo == A. theme_validation calls Tue 10-13 (tonight_check metrics)
SELECT count(*) n, count(*) FILTER (WHERE stop_reason='end_turn') end_turn, count(*) FILTER (WHERE stop_reason='max_tokens') max_tok,
  count(*) FILTER (WHERE output_tokens>25) gt25, count(*) FILTER (WHERE output_tokens>50) gt50, count(*) FILTER (WHERE output_tokens>100) gt100,
  percentile_disc(0.9) WITHIN GROUP (ORDER BY output_tokens) p90, round(avg(output_tokens),1) mean, max(output_tokens) mx, round(sum(cost_usd)::numeric,3) cost,
  min(created_at AT TIME ZONE 'America/New_York') first_et, max(created_at AT TIME ZONE 'America/New_York') last_et
FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13';
\echo == A2. model x stop_reason
SELECT model, stop_reason, count(*), max(output_tokens) mx FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13' GROUP BY 1,2;
\echo == A3. calls by hour:minute-bucket (when the passes ran)
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI') hhmm, count(*) n FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13' GROUP BY 1 ORDER BY 1;
\echo == B. removals Tue 10-13
SELECT count(*) removals FROM mi_audit_log WHERE event_type='ticker_revalidated_out' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13';
\echo == B2. removal detail
SELECT created_at AT TIME ZONE 'America/New_York' at_et, summary, left(detail::text,300) det FROM mi_audit_log WHERE event_type='ticker_revalidated_out' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13' ORDER BY created_at;
\echo == C. alarms Tue 10-13 (alarm query widened)
SELECT event_type, count(*) FROM mi_audit_log WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13'
  AND (event_type IN ('llm_truncation_live','llm_refusal') OR event_type ILIKE '%near_ceiling%' OR event_type ILIKE '%trunc%' OR event_type ILIKE '%refus%' OR event_type ILIKE '%validation%error%' OR (event_type ILIKE '%validation%' AND summary ILIKE '%parse%'))
GROUP BY 1 ORDER BY 1;
\echo == D. validation/rewrite/theme-job audit event types Tue 10-13
SELECT event_type, count(*) FROM mi_audit_log WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13'
  AND (event_type ILIKE '%valid%' OR event_type ILIKE '%rewrite%' OR event_type ILIKE '%synth%' OR event_type ILIKE '%parent%' OR event_type ILIKE '%narrative%' OR event_type ILIKE '%error%' OR event_type ILIKE '%fail%' OR event_type ILIKE '%cooldown%') GROUP BY 1 ORDER BY 1;
\echo == E. rewrite_adopted rows Tue 10-13 and since 10-10
SELECT created_at AT TIME ZONE 'America/New_York' at_et, summary, left(detail::text,400) det FROM mi_audit_log WHERE event_type='llm_request_rewrite_adopted' AND created_at >= '2026-10-10' ORDER BY created_at;
\echo == F. four jobs + validator: api_usage per caller Tue 10-13 (17:00-19:00 ET window and whole day)
SELECT caller, model, stop_reason, count(*) n, round(avg(output_tokens),1) mean_out, max(output_tokens) mx_out, round(sum(cost_usd)::numeric,3) cost
FROM api_usage WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-13'
  AND (caller IN ('theme_validation','narrative_theme_discovery','theme_synthesis','theme_parent_adjudication') OR caller ILIKE 'theme%' OR caller ILIKE '%narrative%')
GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo == G. job runs Tue 10-13 evening (theme-related)
SELECT job_id, status, started_at AT TIME ZONE 'America/New_York' started_et, finished_at AT TIME ZONE 'America/New_York' fin_et, rows_written, left(coalesce(error_message,''),160) err
FROM mi_job_runs WHERE scheduled_for >= '2026-10-13' OR started_at >= '2026-10-13 12:00-04' ORDER BY started_at;
