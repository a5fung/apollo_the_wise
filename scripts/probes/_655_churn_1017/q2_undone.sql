-- #655 churn re-measure, QUERY 2 of 3: WHICH FOLD MOVES WERE UNDONE WITHIN 2 THEME NIGHTS, AND BY WHAT.
-- READ-ONLY (a read-only transaction). Written 2026-10-16, BEFORE Saturday's data was read. Everything below is the
-- PRE-REGISTRATION made executable: the definitions are fixed here; a result that surprises us changes the reading, not the SQL.
--
-- DECISION IT SERVES (PLAN #655, "PRE-REGISTERED 10-14"): whether to bring him a rule change on how the fold, the description
-- validator and the promote lane interact. BAR (his, pre-set): a rule change goes to him when >= 1 in 3 moves is undone.
-- Reported as n moved, n undone, split by cause. WOULD CHANGE THE DECISION: undone >= 1 in 3 on the COMPLETE-window moves
-- (section 2a) -> bring the table with a rule rec; under 1 in 3 -> the table says "leave it" and rows (a)-(d) stay as watch
-- items. Compare with the pre-fold small-theme removal rate q3 prints before reading much into either number.
--
-- UNIT. A "move" = one stock in the `moved` array of one theme_small_folded row (a stock moved INTO the home). Folds are
-- the dissolved themes (q1). Both counts are printed; the bar is read on MOVES.
-- WINDOW. THEME NIGHT = a distinct mi_themes.theme_date. The window of a fold = the fold night (rows written after the fold
-- step) plus the NEXT TWO theme nights. A fold is COMPLETE when both later nights are in the data. Folds from 10-15 and
-- 10-16 are censored on Saturday (their second night is Mon 10-19 / Tue 10-20): their undone counts are a FLOOR. The bar is
-- read on COMPLETE folds; the censored ones are printed beside it and re-read Tue 10-20 if they could move the verdict.
--
-- A MOVE IS UNDONE (strict, the pre-registered reading) if, inside the window, EITHER
--   V  the stock is removed from its new home by validation: a ticker_revalidated_out row
--      "<stock> removed from '<home>' by validation" written after the fold; OR
--   R  the dissolved theme is RE-MINTED: a non-Retired mi_themes row, not the home, that has the dissolved theme's name OR shares
--      >= 2 members with it, AND is new to the board (not on the previous night's board; the dissolved theme's own name always
--      counts). A row on the fold night counts only when the promote lane wrote it (it runs after the fold step). A row that
--      is the home under a new name (holds >= half the home's roster) is excluded.
--   Sensitivity readings, printed beside it, never instead of it: WIDE = strict + an EXISTING theme that now holds >= 2 of the members
--   + a #491 re-homing move-out of the home. NARROW = V, or an R re-mint that holds THIS stock (the strict reading counts every
--   move of a fold whose dissolved theme came back, even a move whose own stock did not). If the bar is met under one reading and
--   not another, say so in the table; do not pick.
-- CAUSE (exclusive, in this order): validation removal > the way the returning row was written. Writers, by evidence:
--   operator promote   a theme_operator_promoted row that night names it (final='<name>'). The promote lane writes
--                      source='shadow_promoted' for operator promotes too, so the audit row decides, not the source column.
--   promote lane       source='shadow_promoted' and no operator row
--   discovery          a theme_discovered row "New theme: <name> (" that night
--   continuity rename  a theme_renamed_for_continuity row that night arrow-naming it
--   unexplained        none of the above (kept visible on purpose)
--   PASS 1.5 is not a separate arm of "undone": it is the LOOP flag pass1_5_loop = a theme_pass1_5_absorption in the window whose
--   source theme is the dissolved theme or one of its re-mints (it came back and was taken in again). It prints on every row it
--   touches. This is the reading of the pre-registration's "validation vs promote-lane re-mint vs Pass 1.5" used here.
-- BIRTH-GATE VERDICT (section 5a, strict_remints): the theme_birth_gate outcome for the returning name that night. Re-promotion over
--   a Retired tombstone is a FIRST CROSSING for the gate (theme_engine.py:2642-2660, #655 E), so a fold that tombstones a theme puts
--   its promote-lane re-mint in front of the gate. At dedup_only the gate ACTS only on `join` (theme_birth_gate.py:128-133); `birth`
--   and the hold outcomes fall through and the cohort promotes as before. So a re-mint on the board shows `birth` or a hold outcome
--   that this mode does not act on; a `join` there would be a miss. No gate row = the gate was not asked (not a first crossing,
--   or the row is a truncated envelope, counted in section 5c). The string reads lane:outcome/reason->join_target@overlap; join
--   overlap is intersection-over-smaller against the live board (theme_birth_gate.py:112), so a 3-stock cohort with 1 stock in the
--   home is 0.33 and is NOT a join, while a 2-stock cohort with 1 in the home is 0.50 and is. The "more than half already covered
--   -> skip the join check" carve-out (theme_birth_gate.py:114-118, 188-190) is passed only by the discovery lane
--   (theme_engine.py:10484-10487), not by the promote lane (:2651).
--
-- WHAT THIS DOES NOT ANSWER: whether a returning theme is a GOOD theme (section 5 carries the night's G3 read only); whether a
-- validator removal was RIGHT (section 4 puts the tape test and the validator's reason side by side; the rule fork is his);
-- anything about returns on money. Causality is not separated: a re-mint after a fold is "came back", not "came back because of".
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

-- :moves = :folds + every moved stock, every way it can be undone, and the per-move verdict (pm).
SELECT :'folds' || $m$ ,
mv AS (
  SELECT w2.id AS fold_id, w2.ts, w2.fd, w2.theme, w2.home, w2.j, w2.mem, w2.prev_night, w2.wend,
         w2.complete, w2.nights_after, w2.latest_night, x AS stock
  FROM w2, json_array_elements_text(w2.j->'moved') AS x),
val AS (
  SELECT m.fold_id, m.stock, min(a.created_at) AS vts
  FROM mv m
  JOIN mi_audit_log a
    ON a.event_type = 'ticker_revalidated_out'
   AND a.summary = m.stock || ' removed from ''' || m.home || ''' by validation'
   AND a.created_at > m.ts
   AND (a.created_at AT TIME ZONE 'America/New_York')::date <= m.wend
  GROUP BY m.fold_id, m.stock),
rh AS (
  SELECT m.fold_id, m.stock, min(a.created_at) AS rts
  FROM mv m
  JOIN mi_audit_log a
    ON a.event_type = 'theme_member_rehomed'
   AND a.created_at > m.ts
   AND (a.created_at AT TIME ZONE 'America/New_York')::date <= m.wend
   AND starts_with(a.summary, 'Rehome: ''' || m.home || ''' -> ')
   AND substring(a.summary FROM '^Rehome: ''.*?'' -> ''.*?'' ([A-Z0-9.-]+) ') = m.stock
  GROUP BY m.fold_id, m.stock),
rem0 AS (
  SELECT w2.id AS fold_id, t.name AS rname, t.theme_date AS rdate, t.source AS rsource, t.created_at AS rts,
         cardinality(t.tickers) AS rn, t.tickers AS rtk, (t.name = w2.theme) AS same_name,
         NOT EXISTS (SELECT 1 FROM mi_themes pv
                     WHERE pv.name = t.name AND pv.stage <> 'Retired' AND pv.theme_date = w2.prev_night) AS new_to_board
  FROM w2
  JOIN mi_themes t
    ON t.theme_date BETWEEN w2.fd AND w2.wend AND t.stage <> 'Retired' AND cardinality(t.tickers) >= 1
   AND t.name <> w2.home AND (t.theme_date > w2.fd OR t.source = 'shadow_promoted')
  LEFT JOIN LATERAL (SELECT h.tickers AS tk FROM mi_themes h
                     WHERE h.name = w2.home AND h.theme_date = w2.fd AND h.stage <> 'Retired') hr ON true
  WHERE (t.name = w2.theme OR (SELECT count(*) FROM unnest(t.tickers) u WHERE u = ANY (w2.mem)) >= 2)
    AND NOT (hr.tk IS NOT NULL AND 2 * (SELECT count(*) FROM unnest(t.tickers) u WHERE u = ANY (hr.tk)) >= cardinality(hr.tk))),
rem AS (SELECT DISTINCT ON (fold_id, rname) * FROM rem0 ORDER BY fold_id, rname, rdate),
remc AS (
  SELECT r.*, (r.same_name OR r.new_to_board) AS strict,
         CASE
           WHEN EXISTS (SELECT 1 FROM mi_audit_log a WHERE a.event_type = 'theme_operator_promoted'
                        AND (a.created_at AT TIME ZONE 'America/New_York')::date = r.rdate
                        AND position('final=''' || r.rname || '''' IN a.detail) > 0) THEN 'operator promote'
           WHEN r.rsource = 'shadow_promoted' THEN 'promote lane'
           WHEN EXISTS (SELECT 1 FROM mi_audit_log a WHERE a.event_type = 'theme_discovered'
                        AND (a.created_at AT TIME ZONE 'America/New_York')::date = r.rdate
                        AND starts_with(a.summary, 'New theme: ' || r.rname || ' (')) THEN 'discovery'
           WHEN EXISTS (SELECT 1 FROM mi_audit_log a WHERE a.event_type = 'theme_renamed_for_continuity'
                        AND (a.created_at AT TIME ZONE 'America/New_York')::date = r.rdate
                        AND position(chr(8594) || ' ''' || r.rname || '''' IN a.detail) > 0) THEN 'continuity rename'
           ELSE 'unexplained' END AS rcause
  FROM rem r),
bgv AS (
  SELECT r.fold_id, r.rname,
         string_agg(COALESCE((regexp_match(a.summary, '\[([a-z0-9_]+)/([a-z_]+)\]'))[1], '?') || ':' || (e->>'outcome')
                    || '/' || COALESCE(e->>'reason', '?')
                    || COALESCE('->' || (e->>'join_target') || '@' || (e->>'join_overlap'), ''), ' | ' ORDER BY a.id) AS gate
  FROM remc r
  JOIN mi_audit_log a
    ON a.event_type = 'theme_birth_gate' AND (a.created_at AT TIME ZONE 'America/New_York')::date = r.rdate
  CROSS JOIN LATERAL json_array_elements(CASE WHEN left(a.detail, 1) = '[' THEN a.detail::json END) e
  WHERE e->>'name' = r.rname
  GROUP BY r.fold_id, r.rname),
p15f AS (
  SELECT w2.id AS fold_id,
         string_agg(DISTINCT substring(a.detail FROM 't=''(.*?)'' t_score') || ' -> ' || substring(a.detail FROM 'target=''(.*?)'' target_score')
                    || ' @' || (a.created_at AT TIME ZONE 'America/New_York')::date, '; ') AS p15_list
  FROM w2
  JOIN mi_audit_log a
    ON a.event_type = 'theme_pass1_5_absorption' AND a.created_at > w2.ts
   AND (a.created_at AT TIME ZONE 'America/New_York')::date <= w2.wend
  WHERE substring(a.detail FROM 't=''(.*?)'' t_score') = w2.theme
     OR substring(a.detail FROM 't=''(.*?)'' t_score') IN (SELECT c.rname FROM remc c WHERE c.fold_id = w2.id)
  GROUP BY w2.id),
pm AS (
  SELECT m.fold_id, m.fd, m.theme, m.home, m.stock, m.complete, m.nights_after, m.wend, m.latest_night, m.j,
         v.vts, h.rts AS rehome_ts, s.n_strict, s.n_holding, s.strict_list, s.first_cause, l.loose_list, pf.p15_list,
         (v.vts IS NOT NULL OR COALESCE(s.n_holding, 0) > 0) AS undone_narrow,
         (v.vts IS NOT NULL OR COALESCE(s.n_strict, 0) > 0) AS undone,
         (v.vts IS NOT NULL OR COALESCE(s.n_strict, 0) > 0 OR h.rts IS NOT NULL OR l.loose_list IS NOT NULL) AS undone_wide,
         CASE WHEN v.vts IS NOT NULL THEN 'validation removal'
              WHEN COALESCE(s.n_strict, 0) > 0 THEN s.first_cause || ' re-mint'
              ELSE 'not undone' END AS cause,
         (SELECT string_agg(t.name || ' [' || cardinality(t.tickers) || ']', '; ' ORDER BY t.name)
          FROM mi_themes t WHERE t.theme_date = m.latest_night AND t.stage <> 'Retired' AND m.stock = ANY (t.tickers)) AS themes_latest
  FROM mv m
  LEFT JOIN val v ON v.fold_id = m.fold_id AND v.stock = m.stock
  LEFT JOIN rh h ON h.fold_id = m.fold_id AND h.stock = m.stock
  LEFT JOIN LATERAL (
     SELECT count(*) AS n_strict, count(*) FILTER (WHERE m.stock = ANY (c.rtk)) AS n_holding,
            string_agg(c.rname || ' @' || c.rdate || ' [' || c.rcause || ', ' || c.rn || ' members'
                       || COALESCE(', gate ' || g.gate, '') || ']', '; ' ORDER BY c.rdate, c.rname) AS strict_list,
            (array_agg(c.rcause ORDER BY c.rdate, c.rname))[1] AS first_cause
     FROM remc c LEFT JOIN bgv g ON g.fold_id = c.fold_id AND g.rname = c.rname
     WHERE c.fold_id = m.fold_id AND c.strict) s ON true
  LEFT JOIN LATERAL (
     SELECT string_agg(c.rname || ' @' || c.rdate, '; ' ORDER BY c.rdate, c.rname) AS loose_list
     FROM remc c WHERE c.fold_id = m.fold_id AND NOT c.strict) l ON true
  LEFT JOIN p15f pf ON pf.fold_id = m.fold_id) $m$ AS moves \gset

\echo == 1. THE WINDOW OF EACH FOLD (the two later theme nights; a fold is complete when both exist)
:folds
SELECT w2.fd AS fold_night, w2.theme AS dissolved_theme, w2.home, w2.n1 AS later_night_1, w2.n2 AS later_night_2, w2.wend AS window_ends,
       w2.nights_after AS later_nights_seen, w2.complete AS window_complete, w2.latest_night
FROM w2 ORDER BY w2.fd, w2.id;

\echo == 2a. THE BAR. n moved, n undone (strict = pre-registered; wide = sensitivity). Read the bar on line 1.
:moves
SELECT pop.label AS population,
       count(*) AS moves, count(DISTINCT pm.fold_id) AS folds,
       count(*) FILTER (WHERE pm.undone) AS undone_strict,
       round(100.0 * count(*) FILTER (WHERE pm.undone) / NULLIF(count(*), 0), 1) AS pct_strict,
       CASE WHEN count(*) = 0 THEN 'no moves'
            WHEN 3 * count(*) FILTER (WHERE pm.undone) >= count(*) THEN 'BAR MET (>= 1 in 3)' ELSE 'bar not met' END AS bar_strict,
       count(*) FILTER (WHERE pm.undone_wide) AS undone_wide,
       round(100.0 * count(*) FILTER (WHERE pm.undone_wide) / NULLIF(count(*), 0), 1) AS pct_wide,
       CASE WHEN count(*) = 0 THEN 'no moves'
            WHEN 3 * count(*) FILTER (WHERE pm.undone_wide) >= count(*) THEN 'BAR MET (>= 1 in 3)' ELSE 'bar not met' END AS bar_wide,
       count(*) FILTER (WHERE pm.undone_narrow) AS undone_narrow,
       round(100.0 * count(*) FILTER (WHERE pm.undone_narrow) / NULLIF(count(*), 0), 1) AS pct_narrow,
       CASE WHEN count(*) = 0 THEN 'no moves'
            WHEN 3 * count(*) FILTER (WHERE pm.undone_narrow) >= count(*) THEN 'BAR MET (>= 1 in 3)' ELSE 'bar not met' END AS bar_narrow
FROM pm
CROSS JOIN LATERAL (VALUES ('1 COMPLETE window (2 later theme nights seen) - THE BAR IS READ HERE', pm.complete),
                           ('2 ALL moves (censored ones are a floor)', true),
                           ('3 CENSORED only (fewer than 2 later nights seen)', NOT pm.complete)) AS pop(label, inc)
WHERE pop.inc GROUP BY pop.label ORDER BY pop.label;

\echo == 2b. SPLIT BY CAUSE (exclusive; with_pass1_5_loop = the returning theme or the dissolved one was absorbed by Pass 1.5 again inside the window)
:moves
SELECT pop.label AS population, pm.cause, count(*) AS moves,
       count(*) FILTER (WHERE pm.p15_list IS NOT NULL) AS with_pass1_5_loop
FROM pm
CROSS JOIN LATERAL (VALUES ('COMPLETE', pm.complete), ('ALL', true)) AS pop(label, inc)
WHERE pop.inc GROUP BY pop.label, pm.cause ORDER BY pop.label DESC, count(*) DESC, pm.cause;

\echo == 2c. EVERY CAUSE THAT TOUCHED A MOVE (not exclusive; a move can be in several)
:moves
SELECT pop.label AS population,
       count(*) AS moves,
       count(*) FILTER (WHERE pm.vts IS NOT NULL) AS any_validation_removal,
       count(*) FILTER (WHERE COALESCE(pm.n_strict, 0) > 0) AS any_strict_remint,
       count(*) FILTER (WHERE pm.vts IS NOT NULL AND COALESCE(pm.n_strict, 0) > 0) AS both,
       count(*) FILTER (WHERE pm.rehome_ts IS NOT NULL) AS any_rehome_move_out,
       count(*) FILTER (WHERE pm.loose_list IS NOT NULL) AS any_existing_theme_holding_2plus,
       count(*) FILTER (WHERE pm.p15_list IS NOT NULL) AS any_pass1_5_loop,
       count(*) FILTER (WHERE pm.themes_latest IS NULL) AS stock_in_no_theme_at_latest_night
FROM pm
CROSS JOIN LATERAL (VALUES ('COMPLETE', pm.complete), ('ALL', true)) AS pop(label, inc)
WHERE pop.inc GROUP BY pop.label ORDER BY pop.label DESC;

\echo == 2d. BY FOLD NIGHT
:moves
SELECT pm.fd AS fold_night, pm.complete AS window_complete, count(DISTINCT pm.fold_id) AS folds, count(*) AS moves,
       count(*) FILTER (WHERE pm.undone) AS undone_strict, count(*) FILTER (WHERE pm.undone_wide) AS undone_wide
FROM pm GROUP BY pm.fd, pm.complete ORDER BY pm.fd;

\echo == 3. PER DISSOLVED THEME (fold level)
:moves
SELECT w2.fd AS fold_night, w2.theme AS dissolved_theme, w2.home,
       cardinality(w2.mem) AS members,
       (SELECT count(*) FROM pm WHERE pm.fold_id = w2.id) AS moved,
       (SELECT count(*) FROM pm WHERE pm.fold_id = w2.id AND pm.undone) AS moves_undone,
       (SELECT count(*) FROM pm WHERE pm.fold_id = w2.id AND pm.vts IS NOT NULL) AS moves_validation_removed,
       (SELECT string_agg(c.rname || ' @' || c.rdate || ' [' || c.rcause || ']', '; ' ORDER BY c.rdate, c.rname) FROM remc c WHERE c.fold_id = w2.id AND c.strict) AS strict_remints,
       (SELECT string_agg(c.rname || ' @' || c.rdate, '; ' ORDER BY c.rdate, c.rname) FROM remc c WHERE c.fold_id = w2.id AND NOT c.strict) AS existing_themes_holding_2plus,
       (SELECT p15_list FROM p15f WHERE p15f.fold_id = w2.id) AS pass1_5_loop,
       w2.nights_after AS later_nights_seen, w2.complete AS window_complete
FROM w2 ORDER BY w2.fd, w2.id;

\echo == 3b. PER MOVE (the rows behind every count above)
:moves
SELECT pm.fd AS fold_night, pm.theme AS dissolved_theme, pm.home, pm.stock, pm.nights_after AS later_nights_seen,
       pm.undone, pm.undone_wide, pm.undone_narrow, pm.cause,
       (pm.vts AT TIME ZONE 'America/New_York')::timestamp(0)::text AS validation_removed_et,
       (pm.rehome_ts AT TIME ZONE 'America/New_York')::timestamp(0)::text AS rehomed_out_et,
       pm.strict_list AS strict_remints, pm.loose_list AS loose_only_themes_holding_2plus, pm.p15_list AS pass1_5_loop,
       pm.themes_latest AS stock_sits_in_at_latest_night
FROM pm ORDER BY pm.fd, pm.fold_id, pm.stock;

\echo == 4a. ROW (a) fold vs validator: each moved stock the description validator later removed, the tape number the fold used, and the validator reason
:moves
SELECT pm.fd AS fold_night, pm.theme AS dissolved_theme, pm.home, pm.stock,
       (pm.vts AT TIME ZONE 'America/New_York')::timestamp(0)::text AS validator_removed_et,
       to_char(pm.vts AT TIME ZONE 'America/New_York', 'Dy') AS validator_weekday,
       pm.j->'verdicts'->pm.stock->>'path' AS fold_test, round((pm.j->'verdicts'->pm.stock->>'corr')::numeric, 3) AS tape_corr_when_folded,
       c.removal_reason AS validator_reason, c.removal_count, pm.complete AS window_complete
FROM pm
LEFT JOIN mi_validation_cooldowns c ON c.ticker = pm.stock AND c.theme_name = pm.home
WHERE pm.vts IS NOT NULL
ORDER BY pm.fd, pm.fold_id, pm.stock;

\echo == 4b. ROW (a) counts, and homes whose roster the validator tried to mass-remove inside the window
:moves
SELECT count(*) AS moves, count(*) FILTER (WHERE pm.vts IS NOT NULL) AS removed_by_the_description_validator,
       count(*) FILTER (WHERE pm.complete) AS complete_window_moves,
       count(*) FILTER (WHERE pm.complete AND pm.vts IS NOT NULL) AS complete_window_removed,
       (SELECT count(DISTINCT w2.home) FROM w2
         WHERE EXISTS (SELECT 1 FROM mi_audit_log a WHERE a.event_type = 'validation_mass_removal_name_suspect'
                         AND a.created_at > w2.ts AND (a.created_at AT TIME ZONE 'America/New_York')::date <= w2.wend
                         AND position(chr(39) || w2.home || chr(39) IN a.summary) > 0)) AS homes_hit_by_the_mass_removal_tripwire
FROM pm;

\echo == 5a. ROW (b) promote-lane and other re-mints: each returning theme, who wrote it, the birth-gate verdict, the G3 read that night
:moves,
fr AS (
  SELECT DISTINCT ON ((a.created_at AT TIME ZONE 'America/New_York')::date)
         (a.created_at AT TIME ZONE 'America/New_York')::date AS d, a.created_at AS ts
  FROM mi_audit_log a WHERE a.event_type = 'theme_small_fold_ran' ORDER BY (a.created_at AT TIME ZONE 'America/New_York')::date, a.id DESC),
cc AS (
  SELECT DISTINCT ON ((a.created_at AT TIME ZONE 'America/New_York')::date)
         (a.created_at AT TIME ZONE 'America/New_York')::date AS d, a.detail::json AS dj
  FROM mi_audit_log a
  WHERE a.event_type = 'theme_correctness_check' AND (a.created_at AT TIME ZONE 'America/New_York')::time >= TIME '17:00'
  ORDER BY (a.created_at AT TIME ZONE 'America/New_York')::date, a.id DESC)
SELECT w2.fd AS fold_night, w2.theme AS dissolved_theme, w2.home, c.rname AS returning_theme, c.rdate AS returned_night, c.rcause AS written_by,
       c.rsource AS source_column, c.rn AS members, (c.rts AT TIME ZONE 'America/New_York')::time(0)::text AS written_et,
       (c.rts > fr.ts) AS written_after_the_fold_step_that_night, c.strict, g.gate AS birth_gate_verdict,
       z.e->>'pass_g3' AS g3_pass_that_night, round((z.e->>'cohesion')::numeric, 3) AS cohesion, round((z.e->>'c1_p95')::numeric, 3) AS random_p95,
       w2.complete AS fold_window_complete
FROM remc c
JOIN w2 ON w2.id = c.fold_id
LEFT JOIN bgv g ON g.fold_id = c.fold_id AND g.rname = c.rname
LEFT JOIN fr ON fr.d = c.rdate
LEFT JOIN cc ON cc.d = c.rdate
LEFT JOIN LATERAL (SELECT e FROM json_array_elements(cc.dj->'g3'->'themes') e WHERE e->>'name' = c.rname LIMIT 1) z ON true
WHERE c.strict
ORDER BY w2.fd, w2.id, c.rdate, c.rname;

\echo == 5b. ROW (b) the nightly picture: G3 failing themes the promote lane wrote AFTER the fold step (the free night), and how many are re-mints of folded themes
:moves,
fr AS (
  SELECT DISTINCT ON ((a.created_at AT TIME ZONE 'America/New_York')::date)
         (a.created_at AT TIME ZONE 'America/New_York')::date AS d, a.created_at AS ts
  FROM mi_audit_log a WHERE a.event_type = 'theme_small_fold_ran' ORDER BY (a.created_at AT TIME ZONE 'America/New_York')::date, a.id DESC),
cc AS (
  SELECT DISTINCT ON ((a.created_at AT TIME ZONE 'America/New_York')::date)
         (a.created_at AT TIME ZONE 'America/New_York')::date AS d, a.detail::json AS dj
  FROM mi_audit_log a
  WHERE a.event_type = 'theme_correctness_check' AND (a.created_at AT TIME ZONE 'America/New_York')::time >= TIME '17:00'
  ORDER BY (a.created_at AT TIME ZONE 'America/New_York')::date, a.id DESC),
fails AS (
  SELECT cc.d, e->>'name' AS nm FROM cc CROSS JOIN LATERAL json_array_elements(cc.dj->'g3'->'themes') e
  WHERE e->>'pass_g3' = 'false' AND cc.d BETWEEN DATE '2026-10-12' AND DATE '2026-10-16')
SELECT n.d AS night, count(f.nm) AS g3_fails,
       count(f.nm) FILTER (WHERE t.source = 'shadow_promoted') AS fails_whose_row_the_promote_lane_wrote,
       count(f.nm) FILTER (WHERE t.source = 'shadow_promoted' AND t.created_at > fr.ts) AS of_those_written_after_the_fold_step,
       count(f.nm) FILTER (WHERE t.source = 'shadow_promoted' AND t.created_at > fr.ts
                             AND f.nm IN (SELECT c.rname FROM remc c WHERE c.strict)) AS of_those_a_re_mint_of_a_folded_theme,
       count(f.nm) FILTER (WHERE t.source IS DISTINCT FROM 'shadow_promoted') AS fails_whose_row_the_engine_wrote
FROM nights n
LEFT JOIN fails f ON f.d = n.d
LEFT JOIN fr ON fr.d = n.d
LEFT JOIN mi_themes t ON t.name = f.nm AND t.theme_date = f.d AND t.stage <> 'Retired'
WHERE n.d BETWEEN DATE '2026-10-12' AND DATE '2026-10-16'
GROUP BY n.d ORDER BY n.d;

\echo == 5c. birth-gate rows per night and how many were unreadable (truncated), so a missing verdict above can be told from no verdict
:folds
SELECT n.d AS night,
       (SELECT count(*) FROM mi_audit_log a WHERE a.event_type = 'theme_birth_gate' AND (a.created_at AT TIME ZONE 'America/New_York')::date = n.d) AS gate_rows,
       (SELECT count(*) FROM mi_audit_log a WHERE a.event_type = 'theme_birth_gate' AND (a.created_at AT TIME ZONE 'America/New_York')::date = n.d
           AND left(a.detail, 1) <> '[') AS gate_rows_unreadable_truncated
FROM nights n WHERE n.d BETWEEN DATE '2026-10-12' AND DATE '2026-10-16' ORDER BY n.d;

COMMIT;
