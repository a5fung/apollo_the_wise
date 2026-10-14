-- #655 Wed 2026-10-14 night, part 2. READ-ONLY.
\pset format unaligned
\pset fieldsep '\t'
\echo == 1. full detail of tonight folds
SELECT id, detail FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-14 16:30:00-04' ORDER BY id;
\echo == 2. Appalachian theme in mi_themes by date (stage, n, rs, source)
SELECT theme_date, name, stage, array_length(tickers,1) n, rs_avg, source, array_to_string(tickers,',') tk
FROM mi_themes WHERE name='Natural Gas-Weighted Appalachian & Shale E&P Producers' AND theme_date >= '2026-10-06' ORDER BY theme_date;
\echo == 3. Oil Gas Mineral and Royalty Owners history
SELECT theme_date, name, stage, array_length(tickers,1) n, rs_avg, source, array_to_string(tickers,',') tk
FROM mi_themes WHERE name='Oil & Gas Mineral and Royalty Owners' AND theme_date >= '2026-10-01' ORDER BY theme_date;
\echo == 4. all sector-cap events by night since 10-02
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) n
FROM mi_audit_log WHERE event_type LIKE 'theme_sector_cap%' AND created_at >= '2026-10-02' GROUP BY 1,2 ORDER BY 1,2;
\echo == 6. tonight G3 detail: n, rate, fail_list
SELECT id, detail::json->'g3'->>'n_board' nb, detail::json->'g3'->>'n_judgeable' nj, detail::json->'g3'->>'pass' p, detail::json->'g3'->>'rate_pct' r, detail::json->'g3'->>'fail_list' fl
FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-14 16:30:00-04';
\echo == 6b. tonight G3 failing themes: stage, size, cohesion, p95
SELECT e->>'name' name, e->>'stage' stage, e->>'size' size, round((e->>'cohesion')::numeric,3) coh, round((e->>'c1_p95')::numeric,3) p95
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-14 16:30:00-04' AND (e->>'pass_g3')='false' ORDER BY (e->>'size')::int, 1;
\echo == 6c. tonight G3 pass/fail by size bucket
SELECT CASE WHEN (e->>'size')::int <= 3 THEN '2-3' ELSE '4+' END bucket, (e->>'pass_g3') pass, count(*) n
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-14 16:30:00-04' GROUP BY 1,2 ORDER BY 1,2;
\echo == 6d. last night G3 by size bucket (10-13 row)
SELECT CASE WHEN (e->>'size')::int <= 3 THEN '2-3' ELSE '4+' END bucket, (e->>'pass_g3') pass, count(*) n
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-13 16:30:00-04' AND a.created_at < '2026-10-14 00:00:00-04' GROUP BY 1,2 ORDER BY 1,2;
\echo == 7. every folded old theme (10-12 on): stage on 10-14 board
SELECT f.fd, f.old_theme, f.home, (SELECT string_agg(t.theme_date::text || ':' || t.stage || ':' || coalesce(array_length(t.tickers,1),0)::text, ' ') FROM mi_themes t WHERE t.name=f.old_theme AND t.theme_date >= '2026-10-12') old_theme_by_date
FROM (SELECT (created_at AT TIME ZONE 'America/New_York')::date fd, detail::json->>'theme' old_theme, detail::json->>'home' home FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12') f ORDER BY 1,2;
\echo == 8. FOLD-UNDONE CHECK: every moved/released member from every fold since 10-12: still in home on 10-14 board? where now?
WITH f AS (SELECT id, (created_at AT TIME ZONE 'America/New_York')::date fd, detail::json d FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12'),
m AS (SELECT f.id, f.fd, f.d->>'theme' old_theme, f.d->>'home' home, 'moved' kind, x tk FROM f, json_array_elements_text(f.d->'moved') x
      UNION ALL SELECT f.id, f.fd, f.d->>'theme', f.d->>'home', 'released', x FROM f, json_array_elements_text(f.d->'released') x)
SELECT m.fd, m.old_theme, m.home, m.kind, m.tk,
  EXISTS(SELECT 1 FROM mi_themes h WHERE h.name=m.home AND h.theme_date='2026-10-14' AND h.stage<>'Retired' AND m.tk = ANY(h.tickers)) still_in_home_1014,
  (SELECT string_agg(t.name || ' [' || t.stage || ',' || coalesce(array_length(t.tickers,1),0)::text || ']', '; ') FROM mi_themes t WHERE t.theme_date='2026-10-14' AND t.stage<>'Retired' AND m.tk = ANY(t.tickers)) now_in
FROM m ORDER BY m.fd, m.id, m.kind, m.tk;
\echo == 8b. RE-MINT CHECK: active 10-14 themes (not the home) sharing >=2 members with a previously folded theme
WITH f AS (SELECT (created_at AT TIME ZONE 'America/New_York')::date fd, detail::json d FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12'),
mem AS (SELECT f.fd, f.d->>'theme' old_theme, f.d->>'home' home, x tk FROM f, json_array_elements_text(f.d->'members') x)
SELECT mem.fd, mem.old_theme, mem.home, t.name new_name, t.stage, t.source, array_length(t.tickers,1) n, count(DISTINCT mem.tk) overlap, string_agg(DISTINCT mem.tk, ',') ov
FROM mi_themes t JOIN mem ON mem.tk = ANY(t.tickers)
WHERE t.theme_date='2026-10-14' AND t.stage<>'Retired' AND t.name <> mem.home AND t.name <> mem.old_theme
GROUP BY mem.fd, mem.old_theme, mem.home, t.name, t.stage, t.source, t.tickers HAVING count(DISTINCT mem.tk) >= 2 ORDER BY 1,2,4;
\echo == 8c. old folded theme names that are ACTIVE (not Retired) on 10-14
SELECT t.name, t.stage, t.source, array_length(t.tickers,1) n, array_to_string(t.tickers,',') tk
FROM mi_themes t WHERE t.theme_date='2026-10-14' AND t.stage<>'Retired' AND t.name IN (SELECT detail::json->>'theme' FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12') ORDER BY 1;
\echo == 9. homes tonight: roster size 10-13 vs 10-14
SELECT name, theme_date, stage, array_length(tickers,1) n, array_to_string(tickers,',') tk FROM mi_themes
WHERE theme_date >= '2026-10-13' AND name IN (SELECT DISTINCT detail::json->>'home' FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12') ORDER BY name, theme_date;
\echo == 10. G3-failing themes tonight on the 10-14 board: size, source, written-at, 10-13 presence
SELECT t.name, t.stage, array_length(t.tickers,1) n, array_to_string(t.tickers,',') tk, t.source, (t.created_at AT TIME ZONE 'America/New_York')::time(0)::text written,
  (SELECT string_agg(p.stage || ':' || coalesce(array_length(p.tickers,1),0)::text, ',') FROM mi_themes p WHERE p.name=t.name AND p.theme_date='2026-10-13') on_1013,
  (SELECT string_agg(p.stage || ':' || coalesce(array_length(p.tickers,1),0)::text, ',') FROM mi_themes p WHERE p.name=t.name AND p.theme_date='2026-10-12') on_1012
FROM mi_themes t WHERE t.theme_date='2026-10-14' AND t.stage<>'Retired' AND t.name IN (
 SELECT e->>'name' FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
 WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-14 16:30:00-04' AND (e->>'pass_g3')='false') ORDER BY n, t.name;
\echo == 11. tonight births/retire/absorb summaries
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, event_type, left(summary,230) s FROM mi_audit_log WHERE event_type IN ('theme_discovered','theme_retired','theme_auto_retired','theme_pass1_5_absorption','theme_cap_drop','theme_split','theme_thesis_merged') AND created_at >= '2026-10-14 16:30:00-04' ORDER BY id;
\echo == 12. fold-related event types ever by night
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) FROM mi_audit_log WHERE event_type LIKE 'theme_small_fold%' GROUP BY 1,2 ORDER BY 1,2;
\echo == 13. PROMOTE-LANE: shadow_promoted rows on 10-14 board, 2-3 members, written-at vs fold_ran time
SELECT t.name, t.stage, array_length(t.tickers,1) n, array_to_string(t.tickers,',') tk, (t.created_at AT TIME ZONE 'America/New_York')::time(0)::text written,
  (SELECT (created_at AT TIME ZONE 'America/New_York')::time(0)::text FROM mi_audit_log WHERE event_type='theme_small_fold_ran' AND created_at >= '2026-10-14 16:30:00-04' ORDER BY id DESC LIMIT 1) fold_ran_at,
  (SELECT string_agg(p.stage || ':' || coalesce(array_length(p.tickers,1),0)::text, ',') FROM mi_themes p WHERE p.name=t.name AND p.theme_date='2026-10-13') on_1013
FROM mi_themes t WHERE t.theme_date='2026-10-14' AND t.stage<>'Retired' AND t.source='shadow_promoted' AND array_length(t.tickers,1) BETWEEN 2 AND 3 ORDER BY written, t.name;
\echo == 13b. promote-lane and discovery events tonight (id, time, type, summary)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, event_type, left(summary,200) s FROM mi_audit_log
WHERE created_at >= '2026-10-14 16:30:00-04' AND (event_type ILIKE '%promot%' OR event_type IN ('theme_discovery_shadow_ran','theme_birth_gate','theme_renamed_for_continuity')) ORDER BY id;
