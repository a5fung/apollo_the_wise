-- #655 Thu 2026-10-15 night 4, part 1: fold_ran + folds + tonight's theme_correctness_check (G1-G4) + G3 fail list. READ-ONLY. Window >= 16:30 ET Thu.
\pset format unaligned
\pset fieldsep '\t'
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et;
\echo == 1. theme_small_fold_ran / error tonight (full)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, event_type, summary, detail
FROM mi_audit_log WHERE event_type IN ('theme_small_fold_ran','theme_small_fold_error') AND created_at >= '2026-10-15 16:30:00-04' ORDER BY id;
\echo == 2. theme_small_folded rows tonight
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, summary,
 detail::json->>'theme' th, detail::json->>'home' home, detail::json->>'e_code' e, detail::json->>'members' members, detail::json->>'moved' moved, detail::json->>'released' released, detail::json->>'g3' g3
FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-15 16:30:00-04' ORDER BY id;
\echo == 3. theme_correctness_check rows 10-12 on (summary)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, summary
FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-12' ORDER BY id;
\echo == 4. tonight's row: g3 scalars (themes array removed) and g4 / g1 / g2 blocks
SELECT id, (a.detail::jsonb->'g3') - 'themes' AS g3_scalars FROM mi_audit_log a WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-15 16:30:00-04' ORDER BY id;
SELECT id, (a.detail::jsonb->'g4') - 'themes' AS g4_block FROM mi_audit_log a WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-15 16:30:00-04' ORDER BY id;
SELECT id, (a.detail::jsonb->'g1') - 'themes' AS g1_block, (a.detail::jsonb->'g2') - 'themes' AS g2_block FROM mi_audit_log a WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-15 16:30:00-04' ORDER BY id;
\echo == 5. tonight G3 failing themes: stage, size, cohesion, p95
SELECT e->>'name' name, e->>'stage' stage, e->>'size' size, round((e->>'cohesion')::numeric,3) coh, round((e->>'c1_p95')::numeric,3) p95
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-15 16:30:00-04' AND (e->>'pass_g3')='false' ORDER BY (e->>'size')::int, 1;
\echo == 5b. G3 pass/fail by size bucket: tonight, then last night (10-14)
SELECT 'tonight' night, CASE WHEN (e->>'size')::int <= 3 THEN '2-3' ELSE '4+' END bucket, (e->>'pass_g3') pass, count(*) n
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-15 16:30:00-04' GROUP BY 1,2,3
UNION ALL
SELECT 'wed_1014', CASE WHEN (e->>'size')::int <= 3 THEN '2-3' ELSE '4+' END, (e->>'pass_g3'), count(*)
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-14 16:30:00-04' AND a.created_at < '2026-10-15 00:00:00-04' GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo == 6. board by night: active, 2-3 members, <=1, retired
SELECT theme_date, count(*) FILTER (WHERE stage<>'Retired') active, count(*) FILTER (WHERE stage<>'Retired' AND array_length(tickers,1) BETWEEN 2 AND 3) n23,
       count(*) FILTER (WHERE stage<>'Retired' AND coalesce(array_length(tickers,1),0) <= 1) n01, count(*) FILTER (WHERE stage='Retired') retired
FROM mi_themes WHERE theme_date >= '2026-10-09' GROUP BY 1 ORDER BY 1;
\echo == 7. G3-failing themes tonight on the 10-15 board: size, source, written-at vs fold_ran, previous nights
SELECT t.name, t.stage, array_length(t.tickers,1) n, array_to_string(t.tickers,',') tk, t.source, (t.created_at AT TIME ZONE 'America/New_York')::time(0)::text written,
  (SELECT (created_at AT TIME ZONE 'America/New_York')::time(0)::text FROM mi_audit_log WHERE event_type='theme_small_fold_ran' AND created_at >= '2026-10-15 16:30:00-04' ORDER BY id DESC LIMIT 1) fold_ran_at,
  (SELECT string_agg(p.stage || ':' || coalesce(array_length(p.tickers,1),0)::text, ',') FROM mi_themes p WHERE p.name=t.name AND p.theme_date='2026-10-14') on_1014,
  (SELECT string_agg(p.stage || ':' || coalesce(array_length(p.tickers,1),0)::text, ',') FROM mi_themes p WHERE p.name=t.name AND p.theme_date='2026-10-13') on_1013
FROM mi_themes t WHERE t.theme_date='2026-10-15' AND t.stage<>'Retired' AND t.name IN (
 SELECT e->>'name' FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
 WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-15 16:30:00-04' AND (e->>'pass_g3')='false') ORDER BY n, t.name;
