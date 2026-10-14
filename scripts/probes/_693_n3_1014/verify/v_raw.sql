-- #693 night-3 VERIFIER (independent re-derivation from raw rows), ET day 2026-10-14
\pset format unaligned
\pset fieldsep '|'
\echo == V0 columns of api_usage and mi_audit_log
SELECT table_name, string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns
WHERE table_name IN ('api_usage','mi_audit_log') GROUP BY 1 ORDER BY 1;
\echo == V1 population: theme_validation rows 10-14 ET (by model/stop_reason; before market container start 16:03:28Z; outside 17:00-17:15 ET; distinct ids)
SELECT model, stop_reason, count(*) n, count(DISTINCT id) n_ids,
  count(*) FILTER (WHERE created_at < timestamptz '2026-10-14 16:03:28+00') before_deploy_start,
  count(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::time NOT BETWEEN '17:00' AND '17:15') outside_window,
  min(created_at AT TIME ZONE 'America/New_York') first_et, max(created_at AT TIME ZONE 'America/New_York') last_et
FROM api_usage WHERE caller='theme_validation'
  AND created_at >= timestamptz '2026-10-14 00:00 America/New_York' AND created_at < timestamptz '2026-10-15 00:00 America/New_York'
GROUP BY 1,2;
\echo == V2 manual recompute 10-14 vs 10-12 (sum/n, count >25, pct, count at <=10 tokens = bare-answer shape)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n, sum(output_tokens) sum_out,
  round(sum(output_tokens)::numeric / count(*), 2) mean_manual,
  sum(CASE WHEN output_tokens > 25 THEN 1 ELSE 0 END) gt25,
  round(100.0 * sum(CASE WHEN output_tokens > 25 THEN 1 ELSE 0 END) / count(*), 2) pct_gt25,
  sum(CASE WHEN output_tokens <= 10 THEN 1 ELSE 0 END) le10,
  sum(CASE WHEN stop_reason = 'max_tokens' THEN 1 ELSE 0 END) max_tok,
  sum(CASE WHEN stop_reason IS DISTINCT FROM 'end_turn' THEN 1 ELSE 0 END) not_end_turn,
  round(sum(cost_usd)::numeric, 4) cost
FROM api_usage WHERE caller='theme_validation'
  AND created_at >= timestamptz '2026-10-12 00:00 America/New_York' AND created_at < timestamptz '2026-10-15 00:00 America/New_York'
GROUP BY 1 ORDER BY 1;
\echo == V3 10-14 output tokens >25, sorted desc (the thinking tail)
SELECT string_agg(output_tokens::text, ',' ORDER BY output_tokens DESC) FROM api_usage
WHERE caller='theme_validation' AND output_tokens > 25
  AND created_at >= timestamptz '2026-10-14 00:00 America/New_York' AND created_at < timestamptz '2026-10-15 00:00 America/New_York';
\echo == V4 any OTHER validation-like caller 10-14 (rehearsal / replay / probe rows)
SELECT caller, model, count(*), min(created_at AT TIME ZONE 'America/New_York') first_et FROM api_usage
WHERE (caller ILIKE '%valid%' OR caller ILIKE '%replay%' OR caller ILIKE '%probe%' OR caller ILIKE '%693%')
  AND created_at >= timestamptz '2026-10-14 00:00 America/New_York' AND created_at < timestamptz '2026-10-15 00:00 America/New_York'
GROUP BY 1,2 ORDER BY 1,2;
\echo == V5 removals 10-14: count, distinct summaries, detail-format check, cooldown rows, time span
SELECT count(*) n, count(DISTINCT summary) n_distinct,
  count(*) FILTER (WHERE detail LIKE '%validation (claude-sonnet-5-5) flagged as not matching theme%') validator_format,
  (SELECT count(*) FROM mi_audit_log c WHERE c.event_type='validation_cooldown_triggered'
     AND c.created_at >= timestamptz '2026-10-14 00:00 America/New_York' AND c.created_at < timestamptz '2026-10-15 00:00 America/New_York') cooldown_rows,
  min(created_at AT TIME ZONE 'America/New_York') first_et, max(created_at AT TIME ZONE 'America/New_York') last_et
FROM mi_audit_log WHERE event_type='ticker_revalidated_out'
  AND created_at >= timestamptz '2026-10-14 00:00 America/New_York' AND created_at < timestamptz '2026-10-15 00:00 America/New_York';
\echo == V6 hidden-flag paths (flags that do NOT become ticker_revalidated_out rows) on 10-12 and 10-14
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*), left(max(summary),160) sample FROM mi_audit_log
WHERE event_type IN ('validation_mass_removal_name_suspect','validation_removal_shielded','theme_renamed_on_mass_flag',
                     'theme_rename_cap_reached','theme_dissolved_flagged_pair','theme_canonicalize_blocked_mass_evicted')
  AND created_at >= timestamptz '2026-10-12 00:00 America/New_York' AND created_at < timestamptz '2026-10-15 00:00 America/New_York'
GROUP BY 1,2 ORDER BY 1,2;
\echo == V7 every error/failure/refusal/truncation/rate-limit/llm_ event type on ET 10-14 (whole day)
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York') first_et, left(max(summary),120) sample FROM mi_audit_log
WHERE created_at >= timestamptz '2026-10-14 00:00 America/New_York' AND created_at < timestamptz '2026-10-15 00:00 America/New_York'
  AND (event_type ILIKE '%error%' OR event_type ILIKE '%fail%' OR event_type ILIKE '%refus%' OR event_type ILIKE '%trunc%'
       OR event_type ILIKE '%rate_limit%' OR event_type ILIKE '%ceiling%' OR event_type ILIKE '%parse%' OR event_type ILIKE 'llm_%'
       OR event_type ILIKE '%anthropic%' OR event_type ILIKE 'validation%' OR event_type ILIKE '%credit%')
GROUP BY 1 ORDER BY 1;
\echo == V8 DoD live clause on 10-14: four jobs' run events + the between_tools rewrite row (after the 12:03 ET restart)
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York') first_et, left(max(summary),200) sample FROM mi_audit_log
WHERE created_at >= timestamptz '2026-10-14 12:03 America/New_York' AND created_at < timestamptz '2026-10-15 00:00 America/New_York'
  AND (event_type IN ('theme_synthesis_run','theme_parent_pass_ran','narrative_theme_discovery_ran','llm_request_rewrite_adopted'))
GROUP BY 1 ORDER BY 1;
\echo == V9 four jobs' api_usage on 10-14 (stop_reason per caller)
SELECT caller, model, stop_reason, count(*), max(output_tokens) mx FROM api_usage
WHERE caller IN ('theme_validation','narrative_theme_discovery','theme_synthesis','theme_parent_adjudication')
  AND created_at >= timestamptz '2026-10-14 00:00 America/New_York' AND created_at < timestamptz '2026-10-15 00:00 America/New_York'
GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo == V10 now ET
SELECT now() AT TIME ZONE 'America/New_York' now_et;
