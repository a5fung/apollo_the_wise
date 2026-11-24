SET default_transaction_read_only = on;
\echo == merge adjudication calls, last 8 days, by day/model/stop
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, model, stop_reason, count(*), max(output_tokens) maxout, round(avg(output_tokens)) avgout FROM api_usage WHERE caller='theme_merge_adjudication' AND created_at > now()-interval '8 days' GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo == model resolution changes, last 14 days
SELECT to_char(resolved_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') t, role, prev_model, model, source FROM mi_model_resolution WHERE resolved_at > now()-interval '14 days' ORDER BY resolved_at;
