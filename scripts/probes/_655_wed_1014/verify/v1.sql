-- #655 Wed 2026-10-14 VERIFIER v1 (independent re-derivation). READ-ONLY. Re-derives G3 per night from the per-theme arrays,
-- the G3 population vs the raw 10-14 board, row-count/rehearsal checks, and the fold rows against raw mi_themes.
\pset format unaligned
\pset fieldsep '\t'
\echo == V0 clock
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et;
\echo == V1 ALL theme_correctness_check rows 10-10..10-14 ET (any hour), with writer time; dup/rehearsal check
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t_et, (created_at AT TIME ZONE 'America/New_York')::date d_et, left(summary,60) s
FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-10 00:00:00-04' ORDER BY id;
\echo == V2 G3 recomputed from per-theme array, per night (pass=true / judgeable=true+false / null) vs stored scalar
SELECT a.id, (a.created_at AT TIME ZONE 'America/New_York')::date d_et,
  count(*) n_arr,
  count(*) FILTER (WHERE (e->>'pass_g3')='true') n_true,
  count(*) FILTER (WHERE (e->>'pass_g3')='false') n_false,
  count(*) FILTER (WHERE e->>'pass_g3' IS NULL) n_null,
  round(100.0*count(*) FILTER (WHERE (e->>'pass_g3')='true') / NULLIF(count(*) FILTER (WHERE e->>'pass_g3' IS NOT NULL),0),2) pct_judgeable,
  round(100.0*count(*) FILTER (WHERE (e->>'pass_g3')='true') / count(*),2) pct_all,
  max(a.detail::json->'g3'->>'pass') st_pass, max(a.detail::json->'g3'->>'n_judgeable') st_nj, max(a.detail::json->'g3'->>'rate_pct') st_rate,
  max(a.detail::json->>'n_board') st_board
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-12 00:00:00-04'
GROUP BY a.id, 2 ORDER BY a.id;
\echo == V2b the unjudgeable (null) theme(s) per night with size and any reason key
SELECT a.id, (a.created_at AT TIME ZONE 'America/New_York')::date d_et, e::text
FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e
WHERE a.event_type='theme_correctness_check' AND a.created_at >= '2026-10-12 00:00:00-04' AND e->>'pass_g3' IS NULL ORDER BY a.id;
\echo == V3 POPULATION 10-14: G3 names NOT on the raw active 10-14 board
WITH g AS (SELECT e->>'name' name FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e WHERE a.id=(SELECT max(id) FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-14 16:00:00-04')),
b AS (SELECT name FROM mi_themes WHERE theme_date='2026-10-14' AND stage<>'Retired')
(SELECT 'in_g3_not_board' side, name FROM g EXCEPT SELECT 'in_g3_not_board', name FROM b)
UNION ALL
(SELECT 'on_board_not_g3', name FROM b EXCEPT SELECT 'on_board_not_g3', name FROM g);
\echo == V3b counts: raw active board 10-14, distinct names, 2-3 members, 4+, <=1
SELECT count(*) active, count(DISTINCT name) dnames, count(*) FILTER (WHERE array_length(tickers,1) BETWEEN 2 AND 3) n23,
 count(*) FILTER (WHERE array_length(tickers,1) >= 4) n4p, count(*) FILTER (WHERE coalesce(array_length(tickers,1),0) <= 1) n01,
 max(created_at AT TIME ZONE 'America/New_York')::text last_write
FROM mi_themes WHERE theme_date='2026-10-14' AND stage<>'Retired';
\echo == V3c same population check for 10-12 and 10-13 rows (counts of mismatches each way)
WITH r AS (SELECT id, (created_at AT TIME ZONE 'America/New_York')::date d FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-12 00:00:00-04'),
g AS (SELECT r.d, e->>'name' name FROM r JOIN mi_audit_log a ON a.id=r.id, json_array_elements(a.detail::json->'g3'->'themes') e),
b AS (SELECT t.theme_date d, t.name FROM mi_themes t WHERE t.theme_date IN (SELECT d FROM r) AND t.stage<>'Retired')
SELECT d, (SELECT count(*) FROM g g2 WHERE g2.d=x.d) n_g3, (SELECT count(*) FROM b b2 WHERE b2.d=x.d) n_board,
 (SELECT count(*) FROM (SELECT name FROM g g2 WHERE g2.d=x.d EXCEPT SELECT name FROM b b2 WHERE b2.d=x.d) z) g3_not_board,
 (SELECT count(*) FROM (SELECT name FROM b b2 WHERE b2.d=x.d EXCEPT SELECT name FROM g g2 WHERE g2.d=x.d) z) board_not_g3
FROM (SELECT DISTINCT d FROM r) x ORDER BY d;
\echo == V4 fold audit rows 10-10..10-14 at ANY hour (rehearsal/manual-run check): count by ET date + hour
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, extract(hour FROM created_at AT TIME ZONE 'America/New_York') hr, event_type, count(*)
FROM mi_audit_log WHERE event_type LIKE 'theme_small_fold%' AND created_at >= '2026-10-10 00:00:00-04' GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo == V5 tonight's fold rows vs raw mi_themes: old theme 10-13 row + 10-14 row; home 10-13 + 10-14; moved in home?; corr vs bar
WITH f AS (SELECT id, detail::json d FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-14 16:00:00-04')
SELECT f.id, f.d->>'theme' old,
 (SELECT stage||':'||coalesce(array_length(tickers,1),0)||':'||coalesce(array_to_string(tickers,','),'') FROM mi_themes WHERE name=f.d->>'theme' AND theme_date='2026-10-13') old_1013,
 (SELECT stage||':'||coalesce(array_length(tickers,1),0) FROM mi_themes WHERE name=f.d->>'theme' AND theme_date='2026-10-14') old_1014,
 f.d->>'home' home,
 (SELECT stage||':'||array_length(tickers,1) FROM mi_themes WHERE name=f.d->>'home' AND theme_date='2026-10-13') home_1013,
 (SELECT stage||':'||array_length(tickers,1) FROM mi_themes WHERE name=f.d->>'home' AND theme_date='2026-10-14') home_1014,
 (SELECT bool_and(m = ANY(h.tickers)) FROM mi_themes h, json_array_elements_text(f.d->'moved') m WHERE h.name=f.d->>'home' AND h.theme_date='2026-10-14') moved_in_home,
 (SELECT bool_or(r = ANY(h.tickers)) FROM mi_themes h, json_array_elements_text(f.d->'released') r WHERE h.name=f.d->>'home' AND h.theme_date='2026-10-14') released_in_home,
 (SELECT string_agg(k||'='||(v->>'corr')||'/'||(v->>'pass'), ' ') FROM json_each(f.d->'verdicts') AS j(k,v)) verdicts,
 f.d->>'bar' bar, f.d->'g3'->>'pass_g3' g3
FROM f ORDER BY f.id;
\echo == V5b home ecosystem vs old theme ecosystem (theme_ecosystem_assigned rows naming either, latest)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, left(summary,200) s FROM mi_audit_log
WHERE event_type='theme_ecosystem_assigned' AND created_at >= '2026-10-12 00:00:00-04'
  AND (summary ILIKE '%Functional Energy Drink%' OR summary ILIKE '%Off-Price & Specialty%' OR summary ILIKE '%Non-Alcoholic Beverages%' OR summary ILIKE '%Apparel & Fashion Recovery%') ORDER BY id;
\echo == V6 theme engine / fold / correctness timing vs container boot (12:03:28 / 12:06:15 ET): first+last theme audit row tonight
SELECT min(created_at AT TIME ZONE 'America/New_York')::text first_theme_row, max(created_at AT TIME ZONE 'America/New_York')::text last_theme_row, count(*)
FROM mi_audit_log WHERE created_at >= '2026-10-14 12:06:15-04' AND created_at < '2026-10-14 18:00:00-04' AND event_type LIKE 'theme%';
\echo == V6b any theme audit rows between 12:00 and 16:59 ET today (manual rerun check)
SELECT event_type, count(*), min((created_at AT TIME ZONE 'America/New_York')::time(0))::text, max((created_at AT TIME ZONE 'America/New_York')::time(0))::text
FROM mi_audit_log WHERE created_at >= '2026-10-14 12:00:00-04' AND created_at < '2026-10-14 16:59:00-04' AND (event_type LIKE 'theme%' OR event_type LIKE 'shadow_themes%') GROUP BY 1 ORDER BY 1;
