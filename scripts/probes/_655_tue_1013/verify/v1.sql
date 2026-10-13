-- #655 Tue 2026-10-13 VERIFIER (independent re-derive). READ-ONLY.
\pset format unaligned
\pset fieldsep '\t'
\echo == 0 now
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et, current_setting('TimeZone') tz, CURRENT_DATE cd;
\echo == 1 correctness rows per ET night since 09-28 (dup or rehearsal check)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n, min(id) id0, max(id) id1,
       string_agg(substring(summary from 'G3 [0-9]+/[0-9]+ \([0-9.]+%'), ' | ') g3
FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-09-28' GROUP BY 1 ORDER BY 1;
\echo == 2 tonight G3 recompute from per-theme array (56328) and 10-12 (55813)
SELECT a.id, count(*) n_themes, count(*) FILTER (WHERE (e->>'pass_g3')='true') n_pass, count(*) FILTER (WHERE (e->>'pass_g3')='false') n_fail,
       count(*) FILTER (WHERE e->>'pass_g3' IS NULL) n_null,
       round(100.0*count(*) FILTER (WHERE (e->>'pass_g3')='true')/count(*),1) pct
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e WHERE a.id IN (55813,56328) GROUP BY a.id ORDER BY a.id;
\echo == 2b top-level detail keys of 56328 (any rehearsal/dry-run flag?)
SELECT string_agg(k, ',') FROM (SELECT json_object_keys(detail::json) k FROM mi_audit_log WHERE id=56328) x;
\echo == 2c g3 sub-keys
SELECT string_agg(k, ',') FROM (SELECT json_object_keys(detail::json->'g3') k FROM mi_audit_log WHERE id=56328) x;
\echo == 3 board population: G3 theme names vs reconstructed get_active_themes(7) as of 10-13
WITH g3 AS (SELECT e->>'name' name, (e->>'size')::int sz FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e WHERE a.id=56328),
latest AS (SELECT DISTINCT ON (name) name, theme_date, stage, tickers FROM mi_themes WHERE theme_date >= DATE '2026-10-06' ORDER BY name, theme_date DESC),
board AS (SELECT name, theme_date, stage, coalesce(array_length(tickers,1),0) n FROM latest WHERE stage <> 'Retired')
SELECT 'in_g3_not_board' side, g3.name, g3.sz, NULL::date d FROM g3 LEFT JOIN board b USING (name) WHERE b.name IS NULL
UNION ALL SELECT 'in_board_not_g3', b.name, b.n, b.theme_date FROM board b LEFT JOIN g3 USING (name) WHERE g3.name IS NULL
UNION ALL SELECT 'board_count', NULL, count(*)::int, NULL FROM board
UNION ALL SELECT 'board_not_dated_1013', NULL, count(*)::int, NULL FROM board WHERE theme_date <> DATE '2026-10-13'
UNION ALL SELECT 'size_mismatch', g3.name, g3.sz, NULL FROM g3 JOIN board b USING (name) WHERE g3.sz <> b.n;
\echo == 4 mi_themes rows dated 10-13: write-time spread (one run? anything after 17:31?)
SELECT source, stage='Retired' retired, count(*) n, min((created_at AT TIME ZONE 'America/New_York'))::text first_w, max((created_at AT TIME ZONE 'America/New_York'))::text last_w
FROM mi_themes WHERE theme_date='2026-10-13' GROUP BY 1,2 ORDER BY 1,2;
\echo == 4b any name with >1 row dated 10-13
SELECT name, count(*) FROM mi_themes WHERE theme_date='2026-10-13' GROUP BY 1 HAVING count(*)>1;
\echo == 5 Appalachian / gas-E&P lookalike names, 10-06..10-13
SELECT theme_date, id, name, stage, array_length(tickers,1) n, round(rs_avg::numeric,1) rs, source, (created_at AT TIME ZONE 'America/New_York')::text w
FROM mi_themes WHERE theme_date >= '2026-10-06' AND (name ILIKE '%Appalachian%' OR name ILIKE '%Natural Gas%' OR name ILIKE '%Shale%') ORDER BY name, theme_date;
\echo == 6 kept_distinct rows tonight: recompute max corr and count >= bar from member detail
SELECT a.id, a.detail::json->>'source' src, (a.detail::json->>'passed') passed_field, (a.detail::json->>'judged') judged_field,
       count(m.key) n_members, max((m.value->>'corr')::numeric) max_corr, count(*) FILTER (WHERE (m.value->>'corr')::numeric >= (a.detail::json->>'bar')::numeric) n_ge_bar,
       count(*) FILTER (WHERE m.value->>'verdict' <> 'reject') n_not_reject
FROM mi_audit_log a, json_each(a.detail::json->'members') m
WHERE a.event_type='theme_sector_cap_kept_distinct' AND a.created_at >= '2026-10-13 16:30:00-04' AND a.created_at < '2026-10-14 06:00:00-04' GROUP BY a.id, a.detail ORDER BY a.id;
\echo == 6b every sector-cap / cap-drop style event tonight (any name)
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at >= '2026-10-13 16:30:00-04' AND created_at < '2026-10-14 06:00:00-04' AND (event_type ILIKE '%cap%') GROUP BY 1 ORDER BY 1;
\echo == 6c the prior-night drop the 10-12 sweep cites (id 54406)
SELECT id, event_type, (created_at AT TIME ZONE 'America/New_York')::text t, left(summary,220) FROM mi_audit_log WHERE id=54406;
\echo == 7 fold rows tonight: members count, moved in home roster on 10-13, old theme stage on 10-13
WITH f AS (SELECT id, detail::json d FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-13 16:30:00-04' AND created_at < '2026-10-14 06:00:00-04')
SELECT f.id, f.d->>'theme' th, json_array_length(f.d->'members') n_mem, f.d->>'e_code' e,
  (SELECT stage FROM mi_themes WHERE name=f.d->>'theme' AND theme_date='2026-10-13') old_stage_1013,
  (SELECT array_length(tickers,1) FROM mi_themes WHERE name=f.d->>'home' AND theme_date='2026-10-13') home_n_1013,
  (SELECT bool_and(mv = ANY(h.tickers)) FROM json_array_elements_text(f.d->'moved') mv, mi_themes h WHERE h.name=f.d->>'home' AND h.theme_date='2026-10-13') moved_all_in_home,
  (SELECT array_length(tickers,1) FROM mi_themes WHERE name=f.d->>'home' AND theme_date='2026-10-12') home_n_1012
FROM f ORDER BY f.id;
\echo == 7b home theme ecosystems (same-ecosystem check) via theme_ecosystem_assigned or mapping table
SELECT table_name FROM information_schema.tables WHERE table_name ILIKE '%ecosystem%';
\echo == 8 fold_ran rows per night ever + any fold error rows
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*), string_agg(left(summary,140),' | ') FROM mi_audit_log WHERE event_type ILIKE 'theme_small_fold%' GROUP BY 1,2 ORDER BY 1,2;
\echo == 9 theme engine run count tonight (one run, not a rerun)
SELECT event_type, count(*), string_agg(id::text, ',') FROM mi_audit_log WHERE event_type IN ('theme_engine_funnel','theme_load_state','theme_small_fold_ran','theme_correctness_check','theme_auto_retired') AND created_at >= '2026-10-13 00:00:00-04' AND created_at < '2026-10-14 06:00:00-04' GROUP BY 1;
\echo == 10 tonight G3 fails: 17:31 list vs 10-12 list (carried-over fails)
SELECT a.id, e->>'name' name, e->>'size' sz FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.id IN (55813) AND (e->>'pass_g3')='false' ORDER BY 2;
