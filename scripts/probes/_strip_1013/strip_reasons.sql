-- the stripped members and the empty 10-12 shells (read-only)
SELECT column_name FROM information_schema.columns WHERE table_name='mi_validation_cooldowns' ORDER BY ordinal_position;
SELECT * FROM mi_validation_cooldowns
 WHERE theme_name IN ('Cross-Border Remittance & Money Transfer Fintech','Quick-Service & Fast-Casual Restaurant Franchisors','Electronics Manufacturing & IT Hardware Distribution Supply Chain')
 ORDER BY theme_name, removed_at;
SELECT theme_date, count(*) FILTER (WHERE coalesce(array_length(tickers,1),0)=0) AS empty_themes, count(*) AS themes
  FROM mi_themes WHERE theme_date >= '2026-10-01' GROUP BY 1 ORDER BY 1;
