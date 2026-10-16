-- #655 churn re-measure, QUERY 1 of 3: WHAT THE FAIL-ONLY FOLD DID, 10-12..10-16 (the pre-registered population).
-- READ-ONLY (a read-only transaction). Written 2026-10-16, before Saturday's data was read.
--
-- WHAT IT ANSWERS: the denominator for the Saturday table. "n moved" and "n dissolved" must come from one place, derived the
-- same way every time; q2 re-derives them with the identical prelude and q1 is the human-readable listing of it.
--   POPULATION (PLAN #655, "PRE-REGISTERED 10-14"): every stock the fail-only fold MOVED on the 10-12..10-16 theme nights, and
--   every theme it DISSOLVED. One theme_small_folded row = one dissolved theme; its `moved` array = the stocks moved into the
--   home. `already_in_home` (passed because they already sat there) and `released` (failed the membership test, went back to the
--   pool) are listed beside them but are NOT "moved" and are not in the n.
--
-- AUDIT EVENT NAMES, derived from the code (not recalled):
--   theme_small_folded      one row per fold      agents/market_intelligence/audit_events.py:373, written theme_engine.py:9252
--   theme_small_fold_ran    one row per night that had a 2-3-member theme (counts + why-not)   audit_events.py:374, theme_engine.py:9206
--   theme_small_fold_error  the pass raised, nothing folded that night   audit_events.py:375, theme_engine.py:10785
--   A folded INCUMBENT also gets a Retired mi_themes row on the fold night (parent_theme = the home, description names
--   "(#655 fold)"); a theme born the same night that folds gets none (theme_engine.py:9262-9270). Section 5 ties the three together.
--
-- THEME NIGHT = a distinct mi_themes.theme_date (weekday engine runs, as in the 10-10 scope). Fold night = the ET date of the
-- theme_small_folded row. A duplicate row for the same (night, theme) is collapsed to the first and flagged (audit_rows > 1).
--
-- WHAT THIS DOES NOT ANSWER: whether any move was UNDONE (q2), the pre-fold comparison (q3), the four named cases (q4).
-- A fold row whose detail is a truncated envelope (db._fit_audit_detail) reads as an unreadable fold; section 5 counts them,
-- because dropping them silently would shrink the denominator.
BEGIN TRANSACTION READ ONLY;
\pset format unaligned
\pset fieldsep '\t'
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text AS now_et, (SELECT max(theme_date) FROM mi_themes)::text AS latest_theme_night;

-- The shared prelude is defined ONCE, as psql variables, because a read-only transaction cannot hold a temp table.
-- :folds = the fold population and each fold's 2-theme-night window.
SELECT $f$ WITH nights AS (
  SELECT DISTINCT theme_date AS d FROM mi_themes WHERE theme_date >= DATE '2026-10-08'),
fold_raw AS (
  SELECT a.id, a.created_at AS ts, (a.created_at AT TIME ZONE 'America/New_York')::date AS fd, a.detail::json AS j,
         count(*) OVER (PARTITION BY (a.created_at AT TIME ZONE 'America/New_York')::date, (a.detail::json)->>'theme') AS n_rows
  FROM mi_audit_log a
  WHERE a.event_type = 'theme_small_folded'
    AND (a.created_at AT TIME ZONE 'America/New_York')::date BETWEEN DATE '2026-10-12' AND DATE '2026-10-16'),
fold AS (
  SELECT DISTINCT ON (fd, j->>'theme')
         id, ts, fd, n_rows, j->>'theme' AS theme, j->>'home' AS home, j->>'e_code' AS e_code, j,
         ARRAY(SELECT json_array_elements_text(j->'members')) AS mem
  FROM fold_raw WHERE j->>'theme' IS NOT NULL ORDER BY fd, j->>'theme', id),
w AS (
  SELECT f.*,
         (SELECT n.d FROM nights n WHERE n.d > f.fd ORDER BY n.d LIMIT 1) AS n1,
         (SELECT n.d FROM nights n WHERE n.d > f.fd ORDER BY n.d OFFSET 1 LIMIT 1) AS n2,
         (SELECT max(n.d) FROM nights n WHERE n.d < f.fd) AS prev_night,
         (SELECT max(n.d) FROM nights n) AS latest_night
  FROM fold f),
w2 AS (
  SELECT w.*, COALESCE(w.n2, w.latest_night) AS wend, (w.n2 IS NOT NULL) AS complete,
         CASE WHEN w.n1 IS NULL THEN 0 WHEN w.n2 IS NULL THEN 1 ELSE 2 END AS nights_after
  FROM w) $f$ AS folds \gset

\echo == 0. THEME NIGHTS present from 10-08 (a weekend or extra night here would shift the 2-night windows in q2)

SELECT theme_date AS theme_night, count(*) FILTER (WHERE stage <> 'Retired') AS live_rows, count(*) FILTER (WHERE stage = 'Retired') AS retired_rows,
       count(*) FILTER (WHERE stage <> 'Retired' AND cardinality(tickers) BETWEEN 2 AND 3) AS live_2_to_3_members
FROM mi_themes WHERE theme_date >= DATE '2026-10-08' GROUP BY 1 ORDER BY 1;

\echo == 1. THE NIGHTLY HEARTBEAT: theme_small_fold_ran / theme_small_fold_error, 10-12..10-16 (status, small themes, G3 fails, folded, why not)

SELECT x.id, (x.created_at AT TIME ZONE 'America/New_York')::timestamp(0)::text AS et, x.event_type,
       x.dj->>'status' AS status, x.dj->>'small' AS small_themes,
       x.dj->'counts'->>'g3_fail' AS g3_fail, x.dj->'counts'->>'folded' AS folded,
       x.dj->'counts'->>'no_ecosystem' AS no_ecosystem, x.dj->'counts'->>'no_home' AS no_home,
       x.dj->'counts'->>'members_fail_test' AS members_fail_test,
       x.dj->'counts'->>'skipped_protected' AS skipped_protected, x.dj->'counts'->>'skipped_renamed' AS skipped_renamed,
       x.dj->>'g3_rate_pct' AS g3_rate_pct, left(x.summary, 90) AS summary,
       CASE WHEN x.dj IS NULL THEN left(x.detail, 160) END AS error_text
FROM (SELECT a.id, a.created_at, a.event_type, a.summary, a.detail,
             CASE WHEN left(a.detail, 1) = '{' THEN a.detail::json END AS dj
      FROM mi_audit_log a
      WHERE a.event_type IN ('theme_small_fold_ran', 'theme_small_fold_error')
        AND (a.created_at AT TIME ZONE 'America/New_York')::date BETWEEN DATE '2026-10-12' AND DATE '2026-10-16') x
ORDER BY x.id;

\echo == 2. EVERY THEME THE FOLD DISSOLVED (one row each; window_complete = two later theme nights are in the data)
:folds
SELECT w2.fd AS fold_night, w2.theme AS dissolved_theme, w2.e_code, w2.home,
       cardinality(w2.mem) AS members,
       (SELECT count(*) FROM json_array_elements_text(w2.j->'moved')) AS moved,
       (SELECT count(*) FROM json_array_elements_text(w2.j->'already_in_home')) AS already_in_home,
       (SELECT count(*) FROM json_array_elements_text(w2.j->'released')) AS released,
       round((w2.j->'g3'->>'cohesion')::numeric, 3) AS cohesion, round((w2.j->'g3'->>'c1_p95')::numeric, 3) AS random_p95,
       (w2.j->'home_pick'->>'home_members') AS home_size_before, (w2.j->'home_pick'->>'shared') AS shared_with_home,
       EXISTS (SELECT 1 FROM mi_themes t WHERE t.name = w2.theme AND t.theme_date = w2.prev_night AND t.stage <> 'Retired') AS was_on_board_night_before,
       EXISTS (SELECT 1 FROM mi_themes t WHERE t.name = w2.theme AND t.theme_date = w2.fd AND t.stage = 'Retired' AND t.parent_theme = w2.home) AS has_tombstone,
       w2.nights_after AS later_nights_seen, w2.complete AS window_complete, w2.n_rows AS audit_rows
FROM w2 ORDER BY w2.fd, w2.id;

\echo == 3. EVERY MEMBER OF EVERY DISSOLVED THEME: moved / already_in_home / released, with the tape test the fold used
:folds
SELECT w2.fd AS fold_night, w2.theme AS dissolved_theme, w2.home, c.cls AS what_happened, c.stock,
       w2.j->'verdicts'->c.stock->>'path' AS membership_test, round((w2.j->'verdicts'->c.stock->>'corr')::numeric, 3) AS tape_corr_at_fold,
       w2.j->'verdicts'->c.stock->>'basket_n' AS basket_n
FROM w2
CROSS JOIN LATERAL (
   SELECT 'moved' AS cls, x AS stock FROM json_array_elements_text(w2.j->'moved') x
   UNION ALL SELECT 'already_in_home', x FROM json_array_elements_text(w2.j->'already_in_home') x
   UNION ALL SELECT 'released', x FROM json_array_elements_text(w2.j->'released') x) c
ORDER BY w2.fd, w2.id, CASE c.cls WHEN 'moved' THEN 0 WHEN 'already_in_home' THEN 1 ELSE 2 END, c.stock;

\echo == 4. TOTALS: n themes dissolved, n stocks moved (this is the denominator for q2), by fold night
:folds,
cs AS (
  SELECT w2.id AS fold_id, w2.fd, c.cls, c.stock
  FROM w2 CROSS JOIN LATERAL (
     SELECT 'moved' AS cls, x AS stock FROM json_array_elements_text(w2.j->'moved') x
     UNION ALL SELECT 'already_in_home', x FROM json_array_elements_text(w2.j->'already_in_home') x
     UNION ALL SELECT 'released', x FROM json_array_elements_text(w2.j->'released') x) c)
SELECT COALESCE(fd::text, 'ALL NIGHTS') AS fold_night,
       count(DISTINCT fold_id) AS themes_dissolved,
       count(*) FILTER (WHERE cls = 'moved') AS n_moved,
       count(DISTINCT stock) FILTER (WHERE cls = 'moved') AS distinct_stocks_moved,
       count(*) FILTER (WHERE cls = 'already_in_home') AS already_in_home,
       count(*) FILTER (WHERE cls = 'released') AS released
FROM cs GROUP BY ROLLUP (fd) ORDER BY fd NULLS LAST;

\echo == 5. TIE-OUT per night: fold rows vs the heartbeat vs the Retired rows (a mismatch means a fold is missing from the denominator)
:folds
SELECT n.d AS fold_night,
       (SELECT count(*) FROM fold_raw r WHERE r.fd = n.d) AS fold_audit_rows,
       (SELECT count(*) FROM fold_raw r WHERE r.fd = n.d AND (r.j->>'theme') IS NULL) AS unreadable_rows,
       (SELECT count(*) FROM fold f WHERE f.fd = n.d) AS distinct_folds,
       (SELECT (r.detail::json)->'counts'->>'folded' FROM mi_audit_log r
         WHERE r.event_type = 'theme_small_fold_ran' AND (r.created_at AT TIME ZONE 'America/New_York')::date = n.d
         ORDER BY r.id DESC LIMIT 1) AS fold_ran_says_folded,
       (SELECT count(*) FROM mi_themes t WHERE t.theme_date = n.d AND t.stage = 'Retired'
           AND t.description LIKE '%(#655 fold)%') AS tombstones_with_655_note,
       (SELECT count(*) FROM mi_audit_log r WHERE r.event_type = 'theme_small_fold_error'
           AND (r.created_at AT TIME ZONE 'America/New_York')::date = n.d) AS fold_error_rows
FROM nights n WHERE n.d BETWEEN DATE '2026-10-12' AND DATE '2026-10-16' ORDER BY n.d;

COMMIT;
