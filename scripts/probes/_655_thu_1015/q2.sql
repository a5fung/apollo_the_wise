-- #655 Thu 2026-10-15 night 4, part 2: the 'U.S. Apparel & Fashion Recovery' dispersal (tonight) + fold-undone / validator-disagreement refresh for Saturday. READ-ONLY.
\pset format unaligned
\pset fieldsep '\t'
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et;
\echo == 1. board history: apparel theme, furniture theme, Arm B survivor (10-12 on)
SELECT theme_date, name, stage, array_length(tickers,1) n, source, (created_at AT TIME ZONE 'America/New_York')::time(0)::text written, array_to_string(tickers,',') tk
FROM mi_themes WHERE name IN ('U.S. Apparel & Fashion Recovery','Commercial, Office & Home Furniture Retailers and Manufacturers','Consumer Discretionary Cyclical Rebound: Apparel & Home Furnishings') AND theme_date >= '2026-10-12' ORDER BY name, theme_date;
\echo == 2. the removed set: tickers validation removed from the furniture theme tonight (cooldown rows)
SELECT count(DISTINCT ticker) n_removed, string_agg(DISTINCT ticker, ',') tickers FROM mi_validation_cooldowns
WHERE theme_name ILIKE 'Commercial, Office & Home Furniture%' AND (removed_at AT TIME ZONE 'America/New_York')::date='2026-10-15';
\echo == 3. NEW-TO-BOARD TONIGHT: themes active 10-15 whose name was NOT active on 10-14, with overlap against the dispersal pool (removed set UNION old apparel roster 10-14)
WITH rm AS (SELECT DISTINCT ticker tk FROM mi_validation_cooldowns WHERE theme_name ILIKE 'Commercial, Office & Home Furniture%' AND (removed_at AT TIME ZONE 'America/New_York')::date='2026-10-15'),
 old_ap AS (SELECT unnest(tickers) tk FROM mi_themes WHERE name='U.S. Apparel & Fashion Recovery' AND theme_date='2026-10-14' AND stage<>'Retired'),
 pool AS (SELECT tk FROM rm UNION SELECT tk FROM old_ap),
 prior AS (SELECT DISTINCT name FROM mi_themes WHERE theme_date='2026-10-14' AND stage<>'Retired')
SELECT t.name, t.stage, t.source, array_length(t.tickers,1) n, (t.created_at AT TIME ZONE 'America/New_York')::time(0)::text written,
  (SELECT count(*) FROM unnest(t.tickers) u WHERE u IN (SELECT tk FROM pool)) ov_pool,
  (SELECT count(*) FROM unnest(t.tickers) u WHERE u IN (SELECT tk FROM rm)) ov_removed,
  (SELECT count(*) FROM mi_themes q WHERE q.name=t.name AND q.theme_date<'2026-10-15') prior_rows_any_stage,
  array_to_string(t.tickers,',') tk
FROM mi_themes t WHERE t.theme_date='2026-10-15' AND t.stage<>'Retired' AND t.name NOT IN (SELECT name FROM prior) ORDER BY ov_pool DESC, t.name;
\echo == 4. EVERY pool ticker: where it sat on the 10-14 board vs where it sits tonight
WITH rm AS (SELECT DISTINCT ticker tk FROM mi_validation_cooldowns WHERE theme_name ILIKE 'Commercial, Office & Home Furniture%' AND (removed_at AT TIME ZONE 'America/New_York')::date='2026-10-15'),
 old_ap AS (SELECT unnest(tickers) tk FROM mi_themes WHERE name='U.S. Apparel & Fashion Recovery' AND theme_date='2026-10-14' AND stage<>'Retired'),
 pool AS (SELECT tk, bool_or(src='removed') in_removed, bool_or(src='old_apparel') in_old_apparel FROM (SELECT tk,'removed' src FROM rm UNION ALL SELECT tk,'old_apparel' FROM old_ap) x GROUP BY tk)
SELECT p.tk, p.in_removed, p.in_old_apparel,
 coalesce((SELECT string_agg(t.name || ' [' || t.stage || ',' || array_length(t.tickers,1) || ']', '; ') FROM mi_themes t WHERE t.theme_date='2026-10-14' AND t.stage<>'Retired' AND p.tk = ANY(t.tickers)),'-- none --') was_1014,
 coalesce((SELECT string_agg(t.name || ' [' || t.stage || ',' || array_length(t.tickers,1) || ']', '; ') FROM mi_themes t WHERE t.theme_date='2026-10-15' AND t.stage<>'Retired' AND p.tk = ANY(t.tickers)),'-- none --') now_1015
FROM pool p ORDER BY p.tk;
\echo == 5. G3 status tonight for every new-to-board theme with pool overlap >= 1 (from the correctness row)
WITH rm AS (SELECT DISTINCT ticker tk FROM mi_validation_cooldowns WHERE theme_name ILIKE 'Commercial, Office & Home Furniture%' AND (removed_at AT TIME ZONE 'America/New_York')::date='2026-10-15'),
 old_ap AS (SELECT unnest(tickers) tk FROM mi_themes WHERE name='U.S. Apparel & Fashion Recovery' AND theme_date='2026-10-14' AND stage<>'Retired'),
 pool AS (SELECT tk FROM rm UNION SELECT tk FROM old_ap),
 prior AS (SELECT DISTINCT name FROM mi_themes WHERE theme_date='2026-10-14' AND stage<>'Retired'),
 nb AS (SELECT t.name FROM mi_themes t WHERE t.theme_date='2026-10-15' AND t.stage<>'Retired' AND t.name NOT IN (SELECT name FROM prior) AND EXISTS (SELECT 1 FROM unnest(t.tickers) u WHERE u IN (SELECT tk FROM pool)))
SELECT nb.name, z.e->>'stage' stage, z.e->>'size' size, z.e->>'pass_g3' pass_g3, round((z.e->>'cohesion')::numeric,3) coh, round((z.e->>'c1_p95')::numeric,3) p95, (z.e IS NULL) not_in_g3_array
FROM nb LEFT JOIN (SELECT e FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-15 16:30:00-04') z ON (z.e->>'name') = nb.name
ORDER BY nb.name;
\echo == 6. audit trail tonight around the dispersal and the births (excl. per-ticker revalidation noise)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, event_type, left(summary,260) s FROM mi_audit_log
WHERE created_at >= '2026-10-15 16:30:00-04' AND event_type NOT IN ('ticker_revalidated_out','validation_cooldown_triggered','theme_rehome_judged','theme_low_quality_description','theme_score_ties')
 AND (event_type IN ('theme_thesis_merged','theme_auto_retired','validation_mass_removal_name_suspect','theme_birth_gate','theme_discovered','theme_small_fold_ran','theme_small_folded','theme_pass1_5_absorption','theme_renamed_for_continuity','theme_engine_funnel','theme_split','theme_cap_drop','theme_discovery_shadow_ran','theme_merge_distinct')
   OR event_type ILIKE '%promot%' OR summary ILIKE '%graduation%' OR summary ILIKE '%apparel%' OR summary ILIKE '%off-price%' OR summary ILIKE '%footwear%') ORDER BY id;
\echo == 7. REFRESH (a): stocks the fold MOVED since 10-12 that the description validator later removed from the home (cooldown rows after the fold)
WITH f AS (SELECT id, (created_at AT TIME ZONE 'America/New_York')::date fd, created_at ca, detail::json d FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12'),
 m AS (SELECT f.id, f.fd, f.ca, f.d->>'theme' old_theme, f.d->>'home' home, x tk FROM f, json_array_elements_text(f.d->'moved') x)
SELECT m.fd, m.old_theme, m.home, m.tk,
 (SELECT string_agg((c.removed_at AT TIME ZONE 'America/New_York')::date::text, ',') FROM mi_validation_cooldowns c WHERE c.ticker=m.tk AND c.theme_name=m.home AND c.removed_at > m.ca) removed_from_home_on,
 EXISTS(SELECT 1 FROM mi_themes h WHERE h.name=m.home AND h.theme_date='2026-10-15' AND h.stage<>'Retired' AND m.tk = ANY(h.tickers)) still_in_home_1015
FROM m ORDER BY m.fd, m.id, m.tk;
\echo == 8. REFRESH (b): re-mints of folded/dissolved themes (active 10-15 themes sharing >=2 members with a previously folded theme, not the home)
WITH f AS (SELECT (created_at AT TIME ZONE 'America/New_York')::date fd, detail::json d FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12'),
mem AS (SELECT f.fd, f.d->>'theme' old_theme, f.d->>'home' home, x tk FROM f, json_array_elements_text(f.d->'members') x)
SELECT mem.fd, mem.old_theme, mem.home, t.name new_name, t.stage, t.source, array_length(t.tickers,1) n, count(DISTINCT mem.tk) overlap, string_agg(DISTINCT mem.tk, ',') ov
FROM mi_themes t JOIN mem ON mem.tk = ANY(t.tickers)
WHERE t.theme_date='2026-10-15' AND t.stage<>'Retired' AND t.name <> mem.home AND t.name <> mem.old_theme
GROUP BY mem.fd, mem.old_theme, mem.home, t.name, t.stage, t.source, t.tickers HAVING count(DISTINCT mem.tk) >= 2 ORDER BY 1,2,4;
\echo == 8c. folded old-theme names ACTIVE on 10-15
SELECT t.name, t.stage, t.source, array_length(t.tickers,1) n, array_to_string(t.tickers,',') tk
FROM mi_themes t WHERE t.theme_date='2026-10-15' AND t.stage<>'Retired' AND t.name IN (SELECT detail::json->>'theme' FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12') ORDER BY 1;
\echo == 9. fold counts by night (event_type x night)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) FROM mi_audit_log WHERE event_type LIKE 'theme_small_fold%' GROUP BY 1,2 ORDER BY 1,2;
