-- #655 Mon 2026-10-12 evening verify, part 2. READ-ONLY.
\echo == 1. latest board 10-12 rows for the six folded themes + homes (stage, n, tickers)
SELECT theme_date, name, stage, array_length(tickers,1) n, rs_avg, source, array_to_string(tickers,',') tk
FROM mi_themes WHERE theme_date >= '2026-10-12' AND name IN (
 'Alternative Asset Managers & Private Markets Platforms','Wealth Management & Retail Brokerage Platforms',
 'Diabetes Management Devices (CGM, Insulin Pumps & Delivery)','Medical Device Mean-Reversion & Rotation Recovery',
 'Emerging Medical Device Innovators Breakout','Enterprise Unstructured Data Storage Infrastructure',
 'Cloud Contact Center & CCaaS Communication Platforms','Functional Beverage & Energy Drink Brands',
 'Non-Alcoholic Beverages & Energy Drinks','Orthopedic Surgical Devices & Instruments','Functional Energy Drink Brands') ORDER BY name, theme_date;
\echo == 2. where are the released members on 10-12 board (active themes only)
SELECT t.name, t.stage, array_length(t.tickers,1) n, x.tk
FROM mi_themes t, unnest(t.tickers) x(tk)
WHERE t.theme_date='2026-10-12' AND t.stage<>'Retired' AND x.tk IN ('PS','BBNX','ITGR','QMCO','CELH','PAX','MMED','DXCM','ATEC','INSP','DBX','BOX','COCO','CNMD','SIBN') ORDER BY x.tk, t.name;
\echo == 3. Appalachian theme history (mi_themes)
SELECT theme_date, stage, array_length(tickers,1) n, rs_avg, source, array_to_string(tickers,',') tk
FROM mi_themes WHERE name='Natural Gas-Weighted Appalachian & Shale E&P Producers' ORDER BY theme_date;
\echo == 4. audit rows naming the Appalachian theme since 10-02
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, event_type, left(summary,260) s
FROM mi_audit_log WHERE created_at >= '2026-10-02' AND (summary ILIKE '%Appalachian%' OR detail ILIKE '%Natural Gas-Weighted Appalachian%') ORDER BY id;
\echo == 5. oil_gas group on 10-09 and 10-12 boards (names, stage, n)
SELECT theme_date, name, stage, array_length(tickers,1) n FROM mi_themes
WHERE theme_date IN ('2026-10-09','2026-10-12') AND (name ILIKE '%oil%' OR name ILIKE '%gas%' OR name ILIKE '%crude%' OR name ILIKE '%tanker%' OR name ILIKE '%refin%' OR name ILIKE '%drilling%' OR name ILIKE '%energy%') ORDER BY theme_date, name;
\echo == 6. G3 fail list sizes on 10-12 board
SELECT name, stage, array_length(tickers,1) n, array_to_string(tickers,',') tk, source FROM mi_themes WHERE theme_date='2026-10-12' AND name IN (
'Diagnostic Testing & Lab Equipment Re-Rating','Digital Advertising & Ad-Tech Monetization Platforms','Digital-First Beauty & Cosmetics Brands',
'Enterprise Information Management & Infrastructure Engineering Software','Functional Energy Drink Brands','International Telecom & Cross-Border Communications Services',
'Peptide & Hormone Therapies for Metabolic & Endocrine Disorders','Precision Timing & Motion Control Component Makers',
'Specialty Biopharma Clinical & Commercial Breakouts (Retinal, Pulmonary, Dermatology)') ORDER BY name;
\echo == 7. tonight retire rows (theme_retired, theme_auto_retired) summaries
SELECT id, event_type, left(summary,230) s FROM mi_audit_log WHERE event_type IN ('theme_retired','theme_auto_retired') AND created_at >= '2026-10-12 16:30:00-04' ORDER BY id;
\echo == 8. tonight births (theme_discovered / birth_gate)
SELECT id, event_type, left(summary,230) s FROM mi_audit_log WHERE event_type IN ('theme_discovered','theme_birth_gate') AND created_at >= '2026-10-12 16:30:00-04' ORDER BY id;
\echo == 9. G3 history 10-12 vs prior: fold_ran earlier nights? (should be none before 10-12)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) FROM mi_audit_log WHERE event_type LIKE 'theme_small_fold%' GROUP BY 1,2 ORDER BY 1,2;
\echo == 10. stage of 2-3 member themes tonight and count g3 failing small (board of 10-12)
SELECT stage, count(*) n, count(*) FILTER (WHERE array_length(tickers,1) BETWEEN 2 AND 3) n23 FROM mi_themes WHERE theme_date='2026-10-12' AND stage<>'Retired' GROUP BY 1 ORDER BY 1;
\echo == 11. retired tombstones 10-12 for folded themes
SELECT name, stage, array_length(tickers,1) n, left(description,80) d FROM mi_themes WHERE theme_date='2026-10-12' AND stage='Retired' ORDER BY name;
