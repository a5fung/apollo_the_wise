\pset format unaligned
\pset fieldsep '|'
\echo == CTX1 per-ET-day theme_validation metrics 10-05..10-14 (same columns as the gate)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n, count(*) FILTER (WHERE stop_reason='max_tokens') max_tok,
  count(*) FILTER (WHERE output_tokens>25) gt25, round(100.0*count(*) FILTER (WHERE output_tokens>25)/count(*),1) pct_gt25,
  round(avg(output_tokens),1) mean, percentile_disc(0.9) WITHIN GROUP (ORDER BY output_tokens) p90, max(output_tokens) mx,
  round(sum(cost_usd)::numeric,3) cost, min(created_at AT TIME ZONE 'America/New_York') first_t, max(created_at AT TIME ZONE 'America/New_York') last_t
FROM api_usage WHERE caller='theme_validation' AND created_at >= '2026-10-05' GROUP BY 1 ORDER BY 1;
\echo == CTX2 10-14 model + stop_reason
SELECT model, stop_reason, count(*), min(created_at AT TIME ZONE 'America/New_York') first_at, max(created_at AT TIME ZONE 'America/New_York') last_at, max(output_tokens) mx
FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-14' GROUP BY 1,2;
\echo == CTX3 10-14 output-token buckets (width 50 from 0; 9/10 tokens = no thinking, empty answer shape)
SELECT CASE WHEN output_tokens<=25 THEN '000-025' WHEN output_tokens<=50 THEN '026-050' WHEN output_tokens<=100 THEN '051-100' WHEN output_tokens<=200 THEN '101-200' ELSE '201+' END b,
  count(*), min(output_tokens), max(output_tokens)
FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-14' GROUP BY 1 ORDER BY 1;
\echo == CTX3b same buckets 10-12
SELECT CASE WHEN output_tokens<=25 THEN '000-025' WHEN output_tokens<=50 THEN '026-050' WHEN output_tokens<=100 THEN '051-100' WHEN output_tokens<=200 THEN '101-200' ELSE '201+' END b,
  count(*), min(output_tokens), max(output_tokens)
FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' GROUP BY 1 ORDER BY 1;
\echo == CTX4 10-14 calls by ET minute
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI') hhmm, count(*), count(*) FILTER (WHERE output_tokens>25) gt25
FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-14' GROUP BY 1 ORDER BY 1;
\echo == CTX5 removals detail 10-14
SELECT created_at AT TIME ZONE 'America/New_York' at_et, summary, detail FROM mi_audit_log
WHERE event_type='ticker_revalidated_out' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-14' ORDER BY created_at;
\echo == CTX6 removals per ET day 10-05..10-14
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) FROM mi_audit_log WHERE event_type='ticker_revalidated_out' AND created_at >= '2026-10-05' GROUP BY 1 ORDER BY 1;
\echo == CTX7 rewrite adopted rows 10-12..now
SELECT created_at AT TIME ZONE 'America/New_York' at_et, summary, left(detail::text,200) det FROM mi_audit_log WHERE event_type='llm_request_rewrite_adopted' AND created_at >= '2026-10-12' ORDER BY created_at;
\echo == CTX8 audit event types 10-14 17:00-18:30 ET
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at AT TIME ZONE 'America/New_York' BETWEEN '2026-10-14 17:00' AND '2026-10-14 18:30' GROUP BY 1 ORDER BY 1;
\echo == CTX9 any error/refusal/truncation event whole ET day 10-14
SELECT event_type, count(*) FROM mi_audit_log WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-14'
 AND (event_type ILIKE '%refus%' OR event_type ILIKE '%trunc%' OR event_type ILIKE '%error%' OR event_type ILIKE '%fail%' OR event_type ILIKE '%near_ceiling%' OR event_type ILIKE '%rate_limit%') GROUP BY 1 ORDER BY 1;
\echo == CTX10 other theme callers 10-14 stop_reason (four jobs: synthesis, parent adjudication, narrative discovery)
SELECT caller, model, stop_reason, count(*), max(output_tokens) mx, min(created_at AT TIME ZONE 'America/New_York') first_at FROM api_usage
WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-14' AND (caller ILIKE 'theme%' OR caller ILIKE '%narrative%' OR caller ILIKE '%synth%' OR caller ILIKE '%validation%')
GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo == CTX11 four named run events on 10-14 and 10-12
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*), min(created_at AT TIME ZONE 'America/New_York') first_at, left(max(summary),240) sample
FROM mi_audit_log WHERE created_at >= '2026-10-12' AND (event_type IN ('theme_synthesis_run','theme_parent_pass_ran') OR event_type ILIKE '%narrative%' OR event_type ILIKE '%discovery%' OR event_type ILIKE '%revalidat%')
GROUP BY 1,2 ORDER BY 1,2;
\echo == CTX12 now ET
SELECT now() AT TIME ZONE 'America/New_York' now_et;
