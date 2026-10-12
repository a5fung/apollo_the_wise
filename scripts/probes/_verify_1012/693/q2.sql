\echo == theme_validation output-token distribution per ET day (thinking-on proxy: share of calls >25 tokens)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n,
  count(*) FILTER (WHERE output_tokens>25) gt25, count(*) FILTER (WHERE output_tokens>50) gt50, count(*) FILTER (WHERE output_tokens>100) gt100,
  percentile_disc(0.5) WITHIN GROUP (ORDER BY output_tokens) p50, percentile_disc(0.9) WITHIN GROUP (ORDER BY output_tokens) p90,
  round(avg(output_tokens),1) mean, max(output_tokens) mx, round(sum(cost_usd)::numeric,3) cost
FROM api_usage WHERE caller='theme_validation' AND created_at >= '2026-09-25' GROUP BY 1 ORDER BY 1;
\echo == any theme_validation call since the Sat 10-10 deploy (expect none until 17:00 ET today)
SELECT count(*) n_since_sat FROM api_usage WHERE caller='theme_validation' AND created_at >= '2026-10-10';
\echo == truncation / parse-error / rewrite rows 10-09..now
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) FROM mi_audit_log
WHERE created_at >= '2026-10-09' AND (event_type IN ('llm_truncation_live','llm_request_rewrite_adopted','llm_refusal','theme_validation_error') OR event_type ILIKE '%validation%error%' OR event_type ILIKE '%near_ceiling%')
GROUP BY 1,2 ORDER BY 1,2;
\echo == now (ET)
SELECT now() AT TIME ZONE 'America/New_York' now_et;
