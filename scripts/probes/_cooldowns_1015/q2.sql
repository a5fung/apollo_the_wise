-- how 17 apparel names landed in the furniture theme (read-only)
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary, 160) AS summary
  FROM mi_audit_log
 WHERE created_at >= now() - interval '4 days'
   AND (summary ILIKE '%Furniture%' OR detail ILIKE '%Commercial, Office & Home Furniture%')
 ORDER BY id;
SELECT theme_date, array_length(tickers,1) n, source, stage, left(array_to_string(tickers, ','), 200) AS tickers
  FROM mi_themes WHERE name = 'Commercial, Office & Home Furniture Retailers and Manufacturers' ORDER BY theme_date DESC LIMIT 6;
