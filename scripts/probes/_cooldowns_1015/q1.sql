-- cooldowns_per_day anomaly 10-15 (read-only): what produced 28 cooldowns today, by cause and theme
SELECT CASE WHEN removal_reason ILIKE 'rehome:%' THEN 'rehome'
            WHEN removal_reason ILIKE 'Description%does not match%' THEN 'validator: description mismatch'
            WHEN removal_reason ILIKE '%fold%' THEN 'fold'
            ELSE left(removal_reason, 40) END AS cause, count(*)
  FROM mi_validation_cooldowns
 WHERE (removed_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-15'
 GROUP BY 1 ORDER BY 2 DESC;
SELECT theme_name, ticker, removed_at AT TIME ZONE 'America/New_York' AS et, left(removal_reason, 110) AS reason
  FROM mi_validation_cooldowns
 WHERE (removed_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-15'
 ORDER BY theme_name, ticker;
SELECT (removed_at AT TIME ZONE 'America/New_York')::date d, count(*) FROM mi_validation_cooldowns
 WHERE removed_at >= now() - interval '21 days' GROUP BY 1 ORDER BY 1;
SELECT caller, count(*) calls, round(avg(output_tokens),1) mean_out
  FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-15' GROUP BY 1;
