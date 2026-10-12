\echo === api_usage today by caller
SELECT caller, count(*), max(created_at AT TIME ZONE 'America/New_York') last_et FROM api_usage WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' GROUP BY 1 ORDER BY 3 DESC;
\echo === ep_grade_judge last 7 days by ET date
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) FROM api_usage WHERE caller='ep_grade_judge' AND created_at > now()-interval '8 days' GROUP BY 1 ORDER BY 1;
\echo === now
SELECT now() AT TIME ZONE 'America/New_York' now_et;
\echo === mi_ep_alerts latest rows
SELECT alert_date, ticker, judge_tier, grade_engine_authority, created_at AT TIME ZONE 'America/New_York' c FROM mi_ep_alerts ORDER BY created_at DESC LIMIT 5;
