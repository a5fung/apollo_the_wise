-- theme_high_strip_rate: how often it fires, and what the 3 flagged 10-09 themes lost (read-only)
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, count(*)
  FROM mi_audit_log WHERE event_type='theme_high_strip_rate' AND created_at >= NOW() - INTERVAL '45 days'
 GROUP BY 1 ORDER BY 1;
SELECT name, theme_date, created_at AT TIME ZONE 'America/New_York' AS created_et, tickers
  FROM mi_themes
 WHERE name IN ('Cross-Border Remittance & Money Transfer Fintech','Quick-Service & Fast-Casual Restaurant Franchisors','Electronics Manufacturing & IT Hardware Distribution Supply Chain')
 ORDER BY name, theme_date;
SELECT theme_name, ticker, removed_at AT TIME ZONE 'America/New_York' AS removed_et, left(reason, 220) AS reason
  FROM mi_validation_cooldowns
 WHERE theme_name IN ('Cross-Border Remittance & Money Transfer Fintech','Quick-Service & Fast-Casual Restaurant Franchisors','Electronics Manufacturing & IT Hardware Distribution Supply Chain')
 ORDER BY theme_name, removed_at;
