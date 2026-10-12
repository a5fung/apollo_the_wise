SELECT name, min(theme_date) first_seen,
  string_agg(CASE WHEN source='shadow_promoted' THEN theme_date::text END, ',' ORDER BY theme_date) shadow_promoted_days,
  (SELECT string_agg(theme_date::text||':'||source, ' ' ORDER BY theme_date) FROM mi_themes y WHERE y.name=x.name AND y.theme_date >= '2026-10-05') recent
FROM mi_themes x
WHERE name IN ('Vertical Commerce & Tax/Payments Software-Fintech Platforms','Cloud Data Storage & Analytics Infrastructure','Cloud Supply Chain & Warehouse Management Software',
 'Cloud Financial Automation & Insurance Core Platform Software','AI Server Power & Signal-Integrity Analog ICs','Exchange, Options Trading & Alternative Consumer Credit Financials')
GROUP BY name ORDER BY name;
