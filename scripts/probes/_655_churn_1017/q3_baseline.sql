-- #655 churn re-measure, QUERY 3 of 3: THE BASELINE - how often a removed theme came back, BEFORE the fold, and the same
-- count AFTER it, measured by ONE set of definitions so the two are comparable. READ-ONLY (a read-only transaction).
-- Written 2026-10-16, BEFORE Saturday's data was read (a pre-registration: the definitions below are fixed now).
--
-- WHAT IT ANSWERS: the PLAN #655 note "PRE-REGISTERED 10-14" asks for n moved / n undone "against the pre-fold baseline of
-- re-mints per night (09-29..10-09, from the 10-10 scope)". This file is that baseline, and the post-fold nights on the same
-- yardstick. Decision it serves: whether the fold's undo rate is worse than the churn that already existed, i.e. whether the
-- Saturday table's rec for rows (a)-(d) is "leave it" or "bring him a rule change" (bar: >= 1 in 3 moves undone, in q2).
--
-- THREE WINDOWS (the `params` rows; engine nights are weekday theme_date values in mi_themes, as in the 10-10 scope):
--   scope_14n     09-22..10-09  CALIBRATION ONLY. Must read 154 exits / 31 same-name returns / 20 new-name re-mints, the figures
--                               printed in scripts/probes/_655_scope/b1_churn.out and docs/analysis/655_scope_small_themes_churn_2026-10-10.md
--                               (the verifier's "29 returns" drops 2 renames; this query does not, so it reads 31). If it does
--                               not, the definitions below have drifted from the scope's and nothing else here can be trusted.
--   pre_fold_9n   09-29..10-09  THE BASELINE the pre-registration names. Returns are only counted up to 10-09, so nothing the
--                               fold did (live from the 10-12 night) can leak in.
--   post_fold_5n  10-12..10-16  the fold era on the same yardstick. Returns are counted up to 10-16.
--
-- DEFINITION A - "as the 10-10 scope defined it" (ported from scripts/probes/_655_scope/b1_churn.py, same board test):
--   on(name, night)  = a non-Retired mi_themes row with >= 1 member that night.
--   EXIT             = on the previous engine night, not on tonight.
--   SAME-NAME RETURN = the exit's name is on again on a LATER engine night inside the window.
--   NEW-NAME RE-MINT = (only when there is no same-name return within 7 calendar days) a name whose FIRST appearance since
--                      06-15 falls in [exit night, exit night + 7 days] and whose first roster has Jaccard >= 0.5 with the
--                      removed theme's roster on the previous night.
--   Per-night view: "arriving" = the night the theme came back (this is the scope's "returns per night");
--                   "from exits tonight" = counted against the night it left.
-- DEFINITION B - the PRE-REGISTERED "undone" yardstick, applied to every removal (so it matches q2):
--   a removal is UNDONE if, within the next 2 engine nights, the same name is on again, OR a theme that was NOT on the
--   previous night's board shares >= 2 members with the removed roster (a same-night row counts only when the promote lane
--   wrote it: that lane runs after the nightly pass). "Loose" drops the not-on-the-board test (any other theme that now holds
--   >= 2 of the members, which also counts an existing theme absorbing them) and is printed beside it, never instead of it.
--   Only removals with 2 later nights inside the window are COMPLETE; the rest are a floor. Size class = members on the
--   previous night: small = 2-3 (the fold's own population), other = everything else.
--
-- WHAT THIS DOES NOT ANSWER: why a theme was removed (the cause-of-exit table is in scripts/probes/_655_scope/b1_churn.out
-- and is not rebuilt here); whether a returning theme was a GOOD theme (q2/q4 carry the G3 read); anything about returns on
-- money (themes are judged on correctness first, not returns). A pre-fold baseline is a different board size and a different
-- regime (rule B went live 10-05; the cap keep-rule and the fold went live 10-12), so a gap is a flag, not a verdict.
-- Window literals are in the params VALUES row of each statement; they are hard-coded on purpose (no psql variables).
BEGIN TRANSACTION READ ONLY;
\pset format unaligned
\pset fieldsep '\t'
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text AS now_et,
       (SELECT max(theme_date) FROM mi_themes)::text AS latest_theme_night,
       (SELECT count(DISTINCT theme_date) FROM mi_themes WHERE theme_date BETWEEN DATE '2026-10-12' AND DATE '2026-10-16') AS post_fold_nights_present;

-- The shared prelude is defined ONCE, as psql variables, because a read-only transaction cannot hold a temp table.
-- :base = engine nights, live board, exits, same-name returns, new-name re-mints (definition A, for all three windows).
SELECT $q$ WITH params(label, w_from, w_to) AS (VALUES
  ('scope_14n',    DATE '2026-09-22', DATE '2026-10-09'),
  ('pre_fold_9n',  DATE '2026-09-29', DATE '2026-10-09'),
  ('post_fold_5n', DATE '2026-10-12', DATE '2026-10-16')),
nights AS (
  SELECT d, lag(d) OVER (ORDER BY d) AS prev
  FROM (SELECT DISTINCT theme_date AS d FROM mi_themes WHERE theme_date >= DATE '2026-06-15') x),
live AS (
  SELECT theme_date AS d, name, source, (SELECT array_agg(DISTINCT u) FROM unnest(tickers) u) AS tk
  FROM mi_themes
  WHERE stage <> 'Retired' AND cardinality(tickers) >= 1 AND theme_date >= DATE '2026-06-15'),
ex AS (
  SELECT p.label, p.w_to, n.d AS bb, n.prev AS a, l.name, l.tk AS last_tk
  FROM params p
  JOIN nights n ON n.d BETWEEN p.w_from AND p.w_to
  JOIN live l ON l.d = n.prev
  WHERE NOT EXISTS (SELECT 1 FROM live l2 WHERE l2.d = n.d AND l2.name = l.name)),
ret0 AS (
  SELECT e.*, (SELECT min(l.d) FROM live l WHERE l.name = e.name AND l.d > e.bb AND l.d <= e.w_to) AS ret_d
  FROM ex e),
ret AS (
  SELECT r0.*, (SELECT l.source FROM live l WHERE l.name = r0.name AND l.d = r0.ret_d) AS ret_src
  FROM ret0 r0),
fs AS (SELECT DISTINCT ON (name) name, d AS fd, tk FROM live ORDER BY name, d),
rm AS (
  SELECT r.label, r.bb, r.a, r.name, r.ret_d, m.nn, m.fd, m.jac
  FROM ret r
  CROSS JOIN LATERAL (
    SELECT f.name AS nn, f.fd,
           round(i.inter::numeric / (cardinality(r.last_tk) + cardinality(f.tk) - i.inter), 2) AS jac
    FROM fs f
    CROSS JOIN LATERAL (SELECT count(*) AS inter FROM unnest(r.last_tk) u WHERE u = ANY (f.tk)) i
    WHERE f.name <> r.name
      AND f.fd BETWEEN r.bb AND LEAST(r.bb + 7, r.w_to)
      AND i.inter::numeric / (cardinality(r.last_tk) + cardinality(f.tk) - i.inter) >= 0.5
    ORDER BY f.fd, f.name
    LIMIT 1) m
  WHERE NOT (r.ret_d IS NOT NULL AND r.ret_d - r.bb <= 7)) $q$ AS base \gset
-- :baseb = :base + the 2-night undone test on every removal (definition B).
SELECT :'base' || $b$ ,
u2 AS (
  SELECT r.label, r.bb, r.a, r.name, r.last_tk, cardinality(r.last_tk) AS sz,
         (SELECT array_agg(x.d ORDER BY x.d) FROM (SELECT d FROM nights WHERE d > r.bb AND d <= r.w_to ORDER BY d LIMIT 2) x) AS nxt
  FROM ret r),
u3 AS (
  SELECT u.*,
         (coalesce(cardinality(u.nxt), 0) = 2) AS complete,
         (u.sz BETWEEN 2 AND 3) AS small,
         EXISTS (SELECT 1 FROM live l WHERE l.name = u.name AND l.d = ANY (u.nxt)) AS back_same_name,
         EXISTS (SELECT 1 FROM live l
                 WHERE l.name <> u.name
                   AND (l.d = ANY (u.nxt) OR (l.d = u.bb AND l.source = 'shadow_promoted'))
                   AND NOT EXISTS (SELECT 1 FROM live pv WHERE pv.name = l.name AND pv.d = u.a)
                   AND (SELECT count(*) FROM unnest(l.tk) t WHERE t = ANY (u.last_tk)) >= 2) AS back_new_name,
         EXISTS (SELECT 1 FROM live l
                 WHERE l.name <> u.name
                   AND (l.d = ANY (u.nxt) OR (l.d = u.bb AND l.source = 'shadow_promoted'))
                   AND (SELECT count(*) FROM unnest(l.tk) t WHERE t = ANY (u.last_tk)) >= 2) AS back_loose_other
  FROM u2 u) $b$ AS baseb \gset

\echo == 1. TOTALS by window (calibration row scope_14n must read 154 / 31 / 20)
:base
SELECT p.label, p.w_from, p.w_to,
       (SELECT count(*) FROM nights n WHERE n.d BETWEEN p.w_from AND p.w_to) AS engine_nights,
       (SELECT count(*) FROM ex e WHERE e.label = p.label) AS exits,
       (SELECT count(*) FROM ret r WHERE r.label = p.label AND r.ret_d IS NOT NULL) AS same_name_returns,
       (SELECT count(*) FROM ret r WHERE r.label = p.label AND r.ret_src = 'shadow_promoted') AS of_those_via_promote_lane_row,
       (SELECT count(DISTINCT r.name) FROM ret r WHERE r.label = p.label AND r.ret_d IS NOT NULL) AS distinct_names_returned,
       (SELECT count(*) FROM rm m WHERE m.label = p.label) AS new_name_remints_7d,
       round(((SELECT count(*) FROM ret r WHERE r.label = p.label AND r.ret_d IS NOT NULL)
            + (SELECT count(*) FROM rm m WHERE m.label = p.label))::numeric
            / NULLIF((SELECT count(*) FROM nights n WHERE n.d BETWEEN p.w_from AND p.w_to), 0), 2) AS returns_per_night
FROM params p ORDER BY p.w_from, p.label;

\echo == 2. PER NIGHT (definition A): returns ARRIVING that night, and returns charged to the night the theme LEFT
:base
SELECT p.label, n.d AS night,
       (SELECT count(*) FROM ex e WHERE e.label = p.label AND e.bb = n.d) AS exits_tonight,
       (SELECT count(*) FROM ret r WHERE r.label = p.label AND r.ret_d = n.d) AS same_name_returns_arriving,
       (SELECT count(*) FROM rm m WHERE m.label = p.label AND m.fd = n.d) AS new_name_remints_arriving,
       (SELECT count(*) FROM ret r WHERE r.label = p.label AND r.bb = n.d AND r.ret_d IS NOT NULL) AS same_name_returns_from_tonights_exits,
       (SELECT count(*) FROM rm m WHERE m.label = p.label AND m.bb = n.d) AS new_name_remints_from_tonights_exits
FROM params p JOIN nights n ON n.d BETWEEN p.w_from AND p.w_to
WHERE p.label <> 'scope_14n'
ORDER BY p.w_from, n.d;

\echo == 3. DEFINITION B, every removal: undone within 2 later nights (strict = same name or a new-to-the-board theme sharing >= 2 members; loose = any other theme holding >= 2). Only complete-window removals feed the percentages
:baseb
SELECT label,
       CASE WHEN GROUPING(small) = 1 THEN 'ALL REMOVALS' WHEN small THEN 'small (2-3 members)' ELSE 'other sizes' END AS removal_size_class,
       count(*) AS removals,
       count(*) FILTER (WHERE complete) AS removals_with_2_later_nights,
       count(*) FILTER (WHERE complete AND (back_same_name OR back_new_name)) AS undone_strict,
       count(*) FILTER (WHERE complete AND back_same_name) AS of_which_same_name,
       count(*) FILTER (WHERE complete AND back_new_name AND NOT back_same_name) AS of_which_new_name_only,
       round(100.0 * count(*) FILTER (WHERE complete AND (back_same_name OR back_new_name))
             / NULLIF(count(*) FILTER (WHERE complete), 0), 1) AS pct_undone_strict,
       count(*) FILTER (WHERE complete AND (back_same_name OR back_loose_other)) AS undone_loose,
       round(100.0 * count(*) FILTER (WHERE complete AND (back_same_name OR back_loose_other))
             / NULLIF(count(*) FILTER (WHERE complete), 0), 1) AS pct_undone_loose,
       count(*) FILTER (WHERE NOT complete AND (back_same_name OR back_new_name)) AS censored_undone_floor,
       count(*) FILTER (WHERE NOT complete) AS censored_removals
FROM u3
GROUP BY GROUPING SETS ((label, small), (label))
ORDER BY label DESC, small NULLS LAST;

\echo == 4. small-theme removals that came back, by window (the rows behind the small line of section 3)
:baseb
SELECT label, bb AS removed_night, name, sz AS members_before, complete,
       back_same_name, back_new_name, back_loose_other
FROM u3
WHERE label IN ('pre_fold_9n', 'post_fold_5n') AND small AND (back_same_name OR back_new_name OR back_loose_other)
ORDER BY label DESC, bb, name;

COMMIT;
