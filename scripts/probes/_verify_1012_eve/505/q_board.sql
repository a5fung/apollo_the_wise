\echo == board counts by date
SELECT theme_date, count(*) n, count(*) FILTER (WHERE stage<>'Retired') live, count(*) FILTER (WHERE stage NOT IN ('Retired','Fading')) active_nonfading,
 count(*) FILTER (WHERE parent_theme IS NOT NULL AND stage<>'Retired') with_parent,
 count(*) FILTER (WHERE source='shadow_promoted' AND stage<>'Retired') shadow_live
FROM mi_themes WHERE theme_date >= '2026-10-07' GROUP BY 1 ORDER BY 1;
\echo == themes of interest on 10-09 and 10-12
SELECT theme_date, name, stage, source, parent_theme, array_length(tickers,1) nt
FROM mi_themes
WHERE theme_date IN ('2026-10-09','2026-10-12') AND name IN (
 'Vertical Commerce & Tax/Payments Software-Fintech Platforms','Cloud Data Storage & Analytics Infrastructure','Cloud Supply Chain & Warehouse Management Software',
 'Cloud Financial Automation & Insurance Core Platform Software','AI Server Power & Signal-Integrity Analog ICs','Exchange, Options Trading & Alternative Consumer Credit Financials',
 'Cross-Border Remittance & Money Transfer Fintech','Brazil Fintech & Digital Banking Rally','Fintech Payments, Prepaid & Consumer Digital Banking Apps',
 'RF, Microwave & Power Semiconductor Specialists','Analog, Mixed-Signal & Power Semiconductor Cyclical Recovery','Functional Beverage & Energy Drink Brands','Non-Alcoholic Beverages & Energy Drinks',
 'Quick-Service & Fast-Casual Restaurant Franchisors','Restaurant Chain Recovery')
ORDER BY name, theme_date;
\echo == audit rows for these since 10-09 (all event types mentioning parent pass or merge)
SELECT id,(created_at AT TIME ZONE 'America/New_York')::text ts, event_type, left(summary,170) s
FROM mi_audit_log WHERE created_at > '2026-10-09 16:00:00-04' AND event_type LIKE 'theme_parent_pass%' ORDER BY id;
\echo == cooldowns touching the dry-run top asks
SELECT theme_a, theme_b, verdict, adjudicated_at::text, cooldown_until::text FROM mi_theme_merge_cooldowns
WHERE theme_a ILIKE '%Remittance%' OR theme_b ILIKE '%Remittance%' OR theme_a ILIKE '%RF, Microwave%' OR theme_b ILIKE '%RF, Microwave%' OR theme_a ILIKE '%Functional Beverage%' OR theme_b ILIKE '%Functional Beverage%' OR theme_a ILIKE '%Quick-Service%' OR theme_b ILIKE '%Quick-Service%' OR theme_a ILIKE '%Fintech Payments, Prepaid%' OR theme_b ILIKE '%Fintech Payments, Prepaid%' ORDER BY adjudicated_at;
