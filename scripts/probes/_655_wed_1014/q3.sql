-- #655 Wed 2026-10-14 VERIFIER (independent re-derive). READ-ONLY.
\pset format unaligned
\pset fieldsep '\t'
\echo == 0 now
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et, current_setting('TimeZone') tz;
\echo == 1 correctness rows per ET night since 09-28 (dup or rehearsal check)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n, min(id) id0, max(id) id1,
       string_agg(substring(summary from 'G3 [0-9]+/[0-9]+ \([0-9.]+%'), ' | ') g3
FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-09-28' GROUP BY 1 ORDER BY 1;
\echo == 2 tonight G3 recompute from per-theme array
SELECT a.id, count(*) n_themes, count(*) FILTER (WHERE (e->>'pass_g3')='true') n_pass, count(*) FILTER (WHERE (e->>'pass_g3')='false') n_fail,
       count(*) FILTER (WHERE e->>'pass_g3' IS NULL) n_null,
       round(100.0*count(*) FILTER (WHERE (e->>'pass_g3')='true')/count(*),1) pct
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-14 16:30:00-04' GROUP BY a.id ORDER BY a.id;
\echo == 2b top-level detail keys of tonight row
SELECT id, string_agg(k, ',') FROM (SELECT id, json_object_keys(detail::json) k FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-14 16:30:00-04') x GROUP BY id;
\echo == 3 board population: G3 theme names vs reconstructed active board as of 10-14
WITH gid AS (SELECT max(id) id FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-14 16:30:00-04'),
g3 AS (SELECT e->>'name' name, (e->>'size')::int sz FROM mi_audit_log a, gid, json_array_elements(a.detail::json->'g3'->'themes') e WHERE a.id=gid.id),
latest AS (SELECT DISTINCT ON (name) name, theme_date, stage, tickers FROM mi_themes WHERE theme_date >= DATE '2026-10-07' ORDER BY name, theme_date DESC),
board AS (SELECT name, theme_date, stage, coalesce(array_length(tickers,1),0) n FROM latest WHERE stage <> 'Retired')
SELECT 'in_g3_not_board' side, g3.name, g3.sz, NULL::date d FROM g3 LEFT JOIN board b USING (name) WHERE b.name IS NULL
UNION ALL SELECT 'in_board_not_g3', b.name, b.n, b.theme_date FROM board b LEFT JOIN g3 USING (name) WHERE g3.name IS NULL
UNION ALL SELECT 'board_count', NULL, count(*)::int, NULL FROM board
UNION ALL SELECT 'board_not_dated_1014', NULL, count(*)::int, NULL FROM board WHERE theme_date <> DATE '2026-10-14'
UNION ALL SELECT 'size_mismatch', g3.name, g3.sz, NULL FROM g3 JOIN board b USING (name) WHERE g3.sz <> b.n;
\echo == 4 mi_themes rows dated 10-14: write-time spread
SELECT source, stage='Retired' retired, count(*) n, min((created_at AT TIME ZONE 'America/New_York'))::text first_w, max((created_at AT TIME ZONE 'America/New_York'))::text last_w
FROM mi_themes WHERE theme_date='2026-10-14' GROUP BY 1,2 ORDER BY 1,2;
\echo == 4b any name with >1 row dated 10-14
SELECT name, count(*) FROM mi_themes WHERE theme_date='2026-10-14' GROUP BY 1 HAVING count(*)>1;
\echo == 5 kept_distinct rows tonight: recompute max corr and count >= bar
SELECT a.id, a.detail::json->>'source' src, (a.detail::json->>'passed') passed_field, (a.detail::json->>'judged') judged_field,
       count(m.key) n_members, max((m.value->>'corr')::numeric) max_corr, count(*) FILTER (WHERE (m.value->>'corr')::numeric >= (a.detail::json->>'bar')::numeric) n_ge_bar,
       count(*) FILTER (WHERE m.value->>'verdict' <> 'reject') n_not_reject
FROM mi_audit_log a, json_each(a.detail::json->'members') m
WHERE a.event_type='theme_sector_cap_kept_distinct' AND a.created_at >= '2026-10-14 16:30:00-04' GROUP BY a.id, a.detail ORDER BY a.id;
\echo == 6 fold rows tonight: members count, moved in home roster on 10-14, old theme stage on 10-14
WITH f AS (SELECT id, detail::json d FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-14 16:30:00-04')
SELECT f.id, f.d->>'theme' th, json_array_length(f.d->'members') n_mem, f.d->>'e_code' e,
  (SELECT stage FROM mi_themes WHERE name=f.d->>'theme' AND theme_date='2026-10-14') old_stage_1014,
  (SELECT array_length(tickers,1) FROM mi_themes WHERE name=f.d->>'home' AND theme_date='2026-10-14') home_n_1014,
  (SELECT bool_and(mv = ANY(h.tickers)) FROM json_array_elements_text(f.d->'moved') mv, mi_themes h WHERE h.name=f.d->>'home' AND h.theme_date='2026-10-14') moved_all_in_home,
  (SELECT array_length(tickers,1) FROM mi_themes WHERE name=f.d->>'home' AND theme_date='2026-10-13') home_n_1013
FROM f ORDER BY f.id;
\echo == 7 engine run count tonight (one run, not a rerun)
SELECT event_type, count(*), string_agg(id::text, ',') FROM mi_audit_log WHERE event_type IN ('theme_engine_funnel','theme_load_state','theme_small_fold_ran','theme_correctness_check','theme_auto_retired') AND created_at >= '2026-10-14 00:00:00-04' GROUP BY 1;
\echo == 8 carried-over G3 fails: tonight vs last night (names failing both)
WITH t AS (SELECT e->>'name' name FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-14 16:30:00-04' AND (e->>'pass_g3')='false'),
y AS (SELECT e->>'name' name FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-13 16:30:00-04' AND a.created_at < '2026-10-14 00:00:00-04' AND (e->>'pass_g3')='false')
SELECT 'fail_both' k, t.name FROM t JOIN y USING (name) UNION ALL SELECT 'fail_tonight_only', t.name FROM t WHERE t.name NOT IN (SELECT name FROM y) UNION ALL SELECT 'fail_last_night_only', y.name FROM y WHERE y.name NOT IN (SELECT name FROM t) ORDER BY 1,2;
