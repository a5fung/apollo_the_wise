\echo == api_usage columns
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='api_usage' ORDER BY ordinal_position;
\echo == theme_validation calls by ET day since 10-01
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n, count(*) FILTER (WHERE stop_reason='end_turn') end_turn,
  count(*) FILTER (WHERE stop_reason='max_tokens') max_tok, round(avg(output_tokens),1) avg_out, max(output_tokens) max_out,
  min(created_at AT TIME ZONE 'America/New_York') first_t, max(created_at AT TIME ZONE 'America/New_York') last_t
FROM api_usage WHERE caller='theme_validation' AND created_at >= '2026-10-01' GROUP BY 1 ORDER BY 1;
\echo == ticker_revalidated_out per ET day since 10-01
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n FROM mi_audit_log
WHERE event_type='ticker_revalidated_out' AND created_at >= '2026-10-01' GROUP BY 1 ORDER BY 1;
