SET default_transaction_read_only = on;
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, caller, model, count(*) FILTER (WHERE stop_reason='refusal') refused, count(*) total FROM api_usage WHERE created_at > now()-interval '10 days' GROUP BY 1,2,3 HAVING count(*) FILTER (WHERE stop_reason='refusal')>0 ORDER BY 1,2;
\echo == haiku-5-5 calls today by stop_reason and hour
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24') h, caller, stop_reason, count(*) FROM api_usage WHERE created_at >= '2026-11-23 00:00-05' AND model='claude-haiku-5-5' GROUP BY 1,2,3 ORDER BY 1,2,3;
