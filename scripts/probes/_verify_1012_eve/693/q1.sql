\echo == api_usage columns
SELECT column_name FROM information_schema.columns WHERE table_name='api_usage' ORDER BY ordinal_position;
\echo == calls by hour ET
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI') hhmm_first, count(*) n FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' GROUP BY 1 ORDER BY 1;
\echo == model + stop_reason
SELECT model, stop_reason, count(*), min(created_at AT TIME ZONE 'America/New_York') first_at, max(created_at AT TIME ZONE 'America/New_York') last_at, max(output_tokens) mx FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' GROUP BY 1,2;
\echo == output token buckets
SELECT width_bucket(output_tokens, ARRAY[10,26,51,101,201,301]) b, count(*), min(output_tokens), max(output_tokens) FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' GROUP BY 1 ORDER BY 1;
\echo == removals detail
SELECT created_at AT TIME ZONE 'America/New_York' at_et, summary, left(details::text,300) det FROM mi_audit_log WHERE event_type='ticker_revalidated_out' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' ORDER BY created_at;
\echo == audit event types containing valid/trunc/refus/thinking/rewrite on 10-12
SELECT event_type, count(*) FROM mi_audit_log WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' AND (event_type ILIKE '%valid%' OR event_type ILIKE '%trunc%' OR event_type ILIKE '%refus%' OR event_type ILIKE '%rewrite%' OR event_type ILIKE '%ceiling%' OR event_type ILIKE '%parse%') GROUP BY 1 ORDER BY 1;
\echo == prior nights same metrics
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n, count(*) FILTER (WHERE stop_reason='max_tokens') max_tok, count(*) FILTER (WHERE output_tokens>25) gt25, round(avg(output_tokens),1) mean FROM api_usage WHERE caller='theme_validation' AND created_at > now() - interval '8 days' GROUP BY 1 ORDER BY 1;
\echo == removals per ET day last 8d
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) FROM mi_audit_log WHERE event_type='ticker_revalidated_out' AND created_at > now() - interval '8 days' GROUP BY 1 ORDER BY 1;
