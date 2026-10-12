\echo === alerts 10-12
SELECT ticker, judge_tier, grade_engine_authority, created_at AT TIME ZONE 'America/New_York' AS created_et FROM mi_ep_alerts WHERE alert_date='2026-10-12' ORDER BY created_at;
\echo === authority distribution last 10 days
SELECT alert_date, count(*) n, count(judge_tier) with_tier, sum((grade_engine_authority='fallback')::int) fb FROM mi_ep_alerts WHERE alert_date>='2026-10-01' GROUP BY 1 ORDER BY 1;
\echo === api_usage ep_grade_judge today (ET)
SELECT caller, count(*), min(created_at AT TIME ZONE 'America/New_York') first_et, max(created_at AT TIME ZONE 'America/New_York') last_et FROM api_usage WHERE (created_at AT TIME ZONE 'America/New_York')::date='2026-10-12' AND caller IN ('ep_grade_judge','mgmt_judge') GROUP BY 1;
