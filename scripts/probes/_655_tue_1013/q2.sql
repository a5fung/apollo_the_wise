-- #655 Tue 2026-10-13 night, part 2. READ-ONLY.
\pset format unaligned
\pset fieldsep '\t'
\echo == 1. full detail of tonight's two folds
SELECT id, detail FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-13 16:30:00-04' ORDER BY id;
\echo == 2. TUESDAY-BOARD CLAUSE: Appalachian theme in mi_themes by date (stage, n, rs, source)
SELECT theme_date, name, stage, array_length(tickers,1) n, rs_avg, source, array_to_string(tickers,',') tk
FROM mi_themes WHERE name='Natural Gas-Weighted Appalachian & Shale E&P Producers' AND theme_date >= '2026-10-06' ORDER BY theme_date;
\echo == 2b. all rows with this name, any date (count, first, last, stages)
SELECT count(*) n, min(theme_date) first_d, max(theme_date) last_d, string_agg(DISTINCT stage, ',') stages FROM mi_themes WHERE name='Natural Gas-Weighted Appalachian & Shale E&P Producers';
\echo == 3. Oil & Gas Mineral and Royalty Owners (also kept tonight) history
SELECT theme_date, name, stage, array_length(tickers,1) n, rs_avg, source, array_to_string(tickers,',') tk
FROM mi_themes WHERE name='Oil & Gas Mineral and Royalty Owners' AND theme_date >= '2026-10-01' ORDER BY theme_date;
\echo == 4. all sector-cap events (dropped/kept/absorbed) by night since 10-02
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) n
FROM mi_audit_log WHERE event_type LIKE 'theme_sector_cap%' AND created_at >= '2026-10-02' GROUP BY 1,2 ORDER BY 1,2;
\echo == 5. audit rows naming the Appalachian theme since 10-12 (id, time, type, summary)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, event_type, left(summary,240) s
FROM mi_audit_log WHERE created_at >= '2026-10-12 12:00:00-04' AND (summary ILIKE '%Appalachian%' OR detail ILIKE '%Natural Gas-Weighted Appalachian%') ORDER BY id;
\echo == 6. tonight G3 detail: n, rate, fail_list
SELECT id, detail::json->'g3'->>'n_board' nb, detail::json->'g3'->>'n_judgeable' nj, detail::json->'g3'->>'pass' p, detail::json->'g3'->>'rate_pct' r, detail::json->'g3'->>'fail_list' fl
FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-13 16:30:00-04';
\echo == 6b. tonight G3 failing themes: stage, size, cohesion, p95
SELECT e->>'name' name, e->>'stage' stage, e->>'size' size, round((e->>'cohesion')::numeric,3) coh, round((e->>'c1_p95')::numeric,3) p95
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-13 16:30:00-04' AND (e->>'pass_g3')='false' ORDER BY (e->>'size')::int, 1;
\echo == 6c. tonight G3 pass/fail by size bucket
SELECT CASE WHEN (e->>'size')::int <= 3 THEN '2-3' ELSE '4+' END bucket, (e->>'pass_g3') pass, count(*) n
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-13 16:30:00-04' GROUP BY 1,2 ORDER BY 1,2;
\echo == 6d. last night's G3 failing themes by size bucket (10-12 row)
SELECT CASE WHEN (e->>'size')::int <= 3 THEN '2-3' ELSE '4+' END bucket, (e->>'pass_g3') pass, count(*) n
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-12 16:30:00-04' AND a.created_at < '2026-10-13 00:00:00-04' GROUP BY 1,2 ORDER BY 1,2;
\echo == 7. last night's six folded themes + tonight's two: stage on 10-13 board (tombstone check)
SELECT name, theme_date, stage, array_length(tickers,1) n, source FROM mi_themes WHERE theme_date >= '2026-10-12' AND name IN (
 'Alternative Asset Managers & Private Markets Platforms','Diabetes Management Devices (CGM, Insulin Pumps & Delivery)','Emerging Medical Device Innovators Breakout',
 'Enterprise Unstructured Data Storage Infrastructure','Functional Beverage & Energy Drink Brands','Orthopedic Surgical Devices & Instruments',
 'Diagnostic Testing & Lab Equipment Re-Rating','Enterprise Information Management & Infrastructure Engineering Software','Functional Energy Drink Brands') ORDER BY name, theme_date;
\echo == 8. where moved/released members sit on the 10-13 board (active themes only)
SELECT x.tk, t.name, t.stage, array_length(t.tickers,1) n
FROM mi_themes t, unnest(t.tickers) x(tk)
WHERE t.theme_date='2026-10-13' AND t.stage<>'Retired' AND x.tk IN ('OMCL','MDLN','QDEL','BSY','OTEX','P') ORDER BY x.tk, t.name;
\echo == 9. homes tonight: roster size 10-12 vs 10-13
SELECT name, theme_date, stage, array_length(tickers,1) n, array_to_string(tickers,',') tk FROM mi_themes
WHERE theme_date >= '2026-10-12' AND name IN ('Medical Device Mean-Reversion & Rotation Recovery','Enterprise HR & Workforce Management SaaS') ORDER BY name, theme_date;
\echo == 10. G3-failing small themes tonight on the 10-13 board: ecosystem + members
SELECT t.name, t.stage, array_length(t.tickers,1) n, array_to_string(t.tickers,',') tk, t.source
FROM mi_themes t WHERE t.theme_date='2026-10-13' AND t.stage<>'Retired' AND t.name IN (
 SELECT e->>'name' FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
 WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-13 16:30:00-04' AND (e->>'pass_g3')='false') ORDER BY t.name;
\echo == 11. tonight births/retire/absorb summaries
SELECT id, event_type, left(summary,230) s FROM mi_audit_log WHERE event_type IN ('theme_discovered','theme_retired','theme_auto_retired','theme_pass1_5_absorption','theme_cap_drop','theme_split','theme_thesis_merged') AND created_at >= '2026-10-13 16:30:00-04' ORDER BY id;
\echo == 12. fold-related event types ever (nights): ran / folded / error counts
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) FROM mi_audit_log WHERE event_type LIKE 'theme_small_fold%' GROUP BY 1,2 ORDER BY 1,2;
