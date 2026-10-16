-- #333: is FMP still failing, and what does FMP itself say the reason is? (read-only)
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, count(*) AS fmp_failures,
       count(*) FILTER (WHERE detail ILIKE '%analyst-estimates%') AS on_analyst_estimates
  FROM mi_audit_log WHERE event_type = 'api_failure_fmp' AND created_at >= now() - interval '14 days'
 GROUP BY 1 ORDER BY 1;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, left(summary, 160) AS summary, left(detail, 700) AS detail
  FROM mi_audit_log WHERE event_type = 'api_failure_fmp' ORDER BY id DESC LIMIT 4;
