\echo === mgmt_judge / ep_grade_judge / judge-ish callers, ET date, last 10 days
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, caller, count(*) FROM api_usage WHERE created_at > now()-interval '10 days' AND (caller LIKE '%judge%') GROUP BY 1,2 ORDER BY 1,2;
\echo === latest judge rows
SELECT caller, created_at AT TIME ZONE 'America/New_York' et FROM api_usage WHERE caller IN ('mgmt_judge','ep_grade_judge') ORDER BY created_at DESC LIMIT 6;
\echo === columns
SELECT column_name FROM information_schema.columns WHERE table_name='api_usage' ORDER BY ordinal_position;
