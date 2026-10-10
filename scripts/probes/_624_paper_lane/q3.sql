CREATE TEMP TABLE d AS SELECT DISTINCT scan_date FROM mi_ep_scan_log WHERE scan_date < '2026-10-10' ORDER BY scan_date DESC LIMIT 30;
\echo === E caller x window (ET) on the 30 scan dates
SELECT caller,
  CASE WHEN (created_at AT TIME ZONE 'America/New_York')::time >= '07:00' AND (created_at AT TIME ZONE 'America/New_York')::time < '10:05' THEN 'scan_0700_1005'
       ELSE 'other' END win,
  count(*) n, round(sum(cost_usd)::numeric,3) cost, round(avg(cost_usd)::numeric,4) avg_cost,
  round(avg(input_tokens)) in_t, round(avg(output_tokens)) out_t, string_agg(DISTINCT model, ',') models
FROM api_usage WHERE (created_at AT TIME ZONE 'America/New_York')::date IN (SELECT scan_date FROM d)
GROUP BY 1,2 ORDER BY 1,2;
\echo === F hourly perplexity_news_search on scan dates
SELECT extract(hour FROM created_at AT TIME ZONE 'America/New_York') h, count(*), round(sum(cost_usd)::numeric,3)
FROM api_usage WHERE caller='perplexity_news_search' AND (created_at AT TIME ZONE 'America/New_York')::date IN (SELECT scan_date FROM d) GROUP BY 1 ORDER BY 1;
\echo === G per-day: graded names vs ep_catalyst_grade calls in window
SELECT d.scan_date,
 (SELECT count(DISTINCT ticker) FROM mi_ep_scan_log s WHERE s.scan_date=d.scan_date AND s.llm_catalyst_quality IS NOT NULL) graded,
 (SELECT count(*) FROM api_usage a WHERE a.caller='ep_catalyst_grade' AND (a.created_at AT TIME ZONE 'America/New_York')::date=d.scan_date) grade_calls,
 (SELECT round(sum(cost_usd)::numeric,3) FROM api_usage a WHERE a.caller IN ('ep_catalyst_grade','perplexity_news_search','perplexity_catalyst_validate','ep_grade_judge','mgmt_judge','catalyst_type_classifier','catalyst_metrics_extractor','ep_theme_fit','judge_divergence') AND (a.created_at AT TIME ZONE 'America/New_York')::date=d.scan_date AND (a.created_at AT TIME ZONE 'America/New_York')::time >= '07:00' AND (a.created_at AT TIME ZONE 'America/New_York')::time < '10:05') ep_window_cost
FROM d ORDER BY 1;
