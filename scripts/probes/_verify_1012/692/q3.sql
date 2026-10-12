\echo == headline questions asked per ET day (api_usage caller=mna_headline_question)
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, count(*) AS n, round(sum(cost_usd)::numeric,3) AS usd FROM api_usage WHERE caller='mna_headline_question' AND created_at >= '2026-10-01' GROUP BY 1 ORDER BY 1;
