-- #655 churn re-measure, QUERY 4: THE TWO NAMED CASES - table row (c) his Capital Markets promotion, row (d) the 10-15 apparel dispersal.
-- READ-ONLY (a read-only transaction). Written 2026-10-16, before Saturday's data was read. Not one of the three queries the task
-- names; it exists because rows (c) and (d) of the one table are not fold moves, so q1-q3 cannot carry their numbers.
--
-- ROW (c): "his own 10-12 promotion 'Capital Markets & Deal-Flow Re-Rating' was absorbed by Pass 1.5 Tue and re-minted with the same
--   members" (PLAN #655, 10-14; absorbed again 10-15, `_655_thu_1015/q2.out`). Measured here: the theme's nightly life from his
--   promotion, every Pass 1.5 / promote / birth-gate row naming it, and the BASE RATE: of ALL operator promotions since 09-01, how many
--   were absorbed by Pass 1.5 within 3 theme nights. A promotion is his ruling that the group is a theme; Pass 1.5 is the nightly
--   rule that a 2-3-member theme with <= 1 unique member is "not a distinct theme" (theme_engine.py:8429-8505, which skips
--   sub-theme parents at :8446 but has no operator-promotion exemption). Whether to add one is his call.
-- ROW (d): the 10-15 apparel dispersal (the cooldowns anomaly he pasted, 28 vs median 5). PLAN #655 says "merge pass 1 glued" the
--   apparel cluster into the furniture theme; the audit trail in `_cooldowns_1015/q3.out` puts the merge in ARM B's thesis merge
--   (theme_merge_pairs_proposed 17:07:09, the 17-name strip 17:07:17.68, theme_thesis_merged 17:07:17.75). That matters: Arm B validates
--   the WINNER'S OLD NAME before the merged name is applied (theme_engine.py:9412 passes winner["name"], and the rename is only
--   applied at :9440 after the validated roster is kept), and that call does NOT pass `mass_flag_out`, so the #214 rename-instead-of-
--   strip arm (built, wired to the Mon/Wed/Fri rescore caller only, theme_engine.py:3824-3828; docs/architecture/theme_engine.md:30)
--   cannot act. 10-15 was a Thursday, so the rescore caller did not run. Section D4 counts how often the tripwire ended in a strip vs
--   a rename, which is the base rate for "built alternative, not wired to this caller".
-- WHAT THIS DOES NOT ANSWER: whether the apparel names belong together (that is the theme engine's judgement and his), whether any
-- promoted theme was a good theme, or what the right fix is. Names are hard-coded from the PLAN note; if a name was changed the
-- section prints no rows and the pool in D3 is empty. Nothing here is a rule change.
BEGIN TRANSACTION READ ONLY;
\pset format unaligned
\pset fieldsep '\t'
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text AS now_et, (SELECT max(theme_date) FROM mi_themes)::text AS latest_theme_night;

\echo == C1. ROW (c) the promoted theme and the theme Pass 1.5 put it into, night by night from 10-09

SELECT t.theme_date AS night, t.name, t.stage, cardinality(t.tickers) AS members, t.source,
       (t.created_at AT TIME ZONE 'America/New_York')::time(0)::text AS written_et, t.parent_theme, array_to_string(t.tickers, ',') AS tickers
FROM mi_themes t
WHERE t.theme_date >= DATE '2026-10-09'
  AND (t.name = 'Capital Markets & Deal-Flow Re-Rating'
       OR t.name IN (SELECT substring(a.detail FROM 'target=''(.*?)'' target_score') FROM mi_audit_log a
                     WHERE a.event_type = 'theme_pass1_5_absorption' AND a.created_at >= TIMESTAMPTZ '2026-10-12 00:00:00-04'
                       AND substring(a.detail FROM 't=''(.*?)'' t_score') = 'Capital Markets & Deal-Flow Re-Rating'))
ORDER BY t.name = 'Capital Markets & Deal-Flow Re-Rating' DESC, t.name, t.theme_date;

\echo == C2. ROW (c) every audit row naming it since 10-12 (operator promotion, Pass 1.5, promote lane, birth gate, folds)

SELECT a.id, (a.created_at AT TIME ZONE 'America/New_York')::timestamp(0)::text AS et, a.event_type, left(a.summary, 230) AS summary
FROM mi_audit_log a
WHERE a.created_at >= TIMESTAMPTZ '2026-10-12 00:00:00-04'
  AND a.event_type IN ('theme_operator_promoted', 'theme_pass1_5_absorption', 'theme_pass1_5_skip', 'shadow_themes_promoted',
                       'theme_birth_gate', 'theme_small_folded', 'theme_retired', 'theme_auto_retired', 'theme_renamed_for_continuity')
  AND (position('Capital Markets & Deal-Flow Re-Rating' IN a.summary) > 0 OR position('Capital Markets & Deal-Flow Re-Rating' IN a.detail) > 0)
ORDER BY a.id;

\echo == C3. ROW (c) BASE RATE, per operator promotion since 09-01: absorbed by Pass 1.5 inside 3 theme nights, retired, still live

WITH nights AS (SELECT DISTINCT theme_date AS d FROM mi_themes WHERE theme_date >= DATE '2026-09-01'),
op AS (
  SELECT a.id, a.created_at AS ts, (a.created_at AT TIME ZONE 'America/New_York')::date AS d,
         substring(a.detail FROM 'final=''(.*?)'' tickers=') AS nm, substring(a.detail FROM 'tickers=(\[.*?\])') AS tk
  FROM mi_audit_log a WHERE a.event_type = 'theme_operator_promoted' AND a.created_at >= TIMESTAMPTZ '2026-09-01'),
op3 AS (
  SELECT op.*, (SELECT n.d FROM nights n WHERE n.d > op.d ORDER BY n.d OFFSET 2 LIMIT 1) AS night3 FROM op)
SELECT op3.d AS promoted_night, op3.nm AS promoted_theme,
       (SELECT string_agg((p.created_at AT TIME ZONE 'America/New_York')::date || ' -> ' || substring(p.detail FROM 'target=''(.*?)'' target_score'), '; ' ORDER BY p.id)
        FROM mi_audit_log p
        WHERE p.event_type = 'theme_pass1_5_absorption' AND substring(p.detail FROM 't=''(.*?)'' t_score') = op3.nm
          AND p.created_at > op3.ts AND (p.created_at AT TIME ZONE 'America/New_York')::date <= COALESCE(op3.night3, (SELECT max(d) FROM nights))) AS absorbed_by_pass1_5_within_3_nights,
       (SELECT string_agg(r.theme_date::text, ',' ORDER BY r.theme_date) FROM mi_themes r
        WHERE r.name = op3.nm AND r.stage = 'Retired' AND r.theme_date > op3.d
          AND r.theme_date <= COALESCE(op3.night3, (SELECT max(d) FROM nights))) AS retired_rows_within_3_nights,
       EXISTS (SELECT 1 FROM mi_themes l WHERE l.name = op3.nm AND l.stage <> 'Retired' AND l.theme_date = (SELECT max(d) FROM nights)) AS live_at_latest_night,
       (op3.night3 IS NOT NULL) AS three_nights_elapsed
FROM op3 ORDER BY op3.d, op3.id;

\echo == C4. ROW (c) BASE RATE total

WITH nights AS (SELECT DISTINCT theme_date AS d FROM mi_themes WHERE theme_date >= DATE '2026-09-01'),
op AS (
  SELECT a.id, a.created_at AS ts, (a.created_at AT TIME ZONE 'America/New_York')::date AS d,
         substring(a.detail FROM 'final=''(.*?)'' tickers=') AS nm
  FROM mi_audit_log a WHERE a.event_type = 'theme_operator_promoted' AND a.created_at >= TIMESTAMPTZ '2026-09-01'),
op3 AS (SELECT op.*, (SELECT n.d FROM nights n WHERE n.d > op.d ORDER BY n.d OFFSET 2 LIMIT 1) AS night3 FROM op),
x AS (
  SELECT op3.*, EXISTS (SELECT 1 FROM mi_audit_log p
                        WHERE p.event_type = 'theme_pass1_5_absorption' AND substring(p.detail FROM 't=''(.*?)'' t_score') = op3.nm
                          AND p.created_at > op3.ts AND (p.created_at AT TIME ZONE 'America/New_York')::date <= op3.night3) AS absorbed
  FROM op3 WHERE op3.night3 IS NOT NULL)
SELECT count(*) AS operator_promotions_with_3_nights_elapsed, count(*) FILTER (WHERE absorbed) AS absorbed_by_pass1_5_within_3_nights,
       (SELECT count(*) FROM op3 WHERE op3.night3 IS NULL) AS promotions_still_inside_3_nights
FROM x;

\echo == D1. ROW (d) the three themes night by night from 10-12

SELECT t.theme_date AS night, t.name, t.stage, cardinality(t.tickers) AS members, t.source, t.parent_theme,
       (t.created_at AT TIME ZONE 'America/New_York')::time(0)::text AS written_et, array_to_string(t.tickers, ',') AS tickers
FROM mi_themes t
WHERE t.theme_date >= DATE '2026-10-12'
  AND t.name IN ('U.S. Apparel & Fashion Recovery', 'Commercial, Office & Home Furniture Retailers and Manufacturers',
                 'Consumer Discretionary Cyclical Rebound: Apparel & Home Furnishings')
ORDER BY t.name, t.theme_date;

\echo == D2. ROW (d) the 10-15 sequence: pairs proposed, the tripwire, the strip, the thesis merge (read the order and the clock times)

SELECT a.id, (a.created_at AT TIME ZONE 'America/New_York')::time(3)::text AS et, a.event_type, left(a.summary, 240) AS summary
FROM mi_audit_log a
WHERE (a.created_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-15'
  AND (a.created_at AT TIME ZONE 'America/New_York')::time BETWEEN TIME '17:00' AND TIME '17:15'
  AND a.event_type IN ('theme_merge_pairs_proposed', 'validation_mass_removal_name_suspect', 'theme_thesis_merged',
                       'theme_merge_dissolved_post_validation', 'theme_renamed_on_mass_flag', 'theme_dissolved_flagged_pair', 'theme_small_folded')
  AND (a.event_type IN ('theme_merge_pairs_proposed', 'theme_small_folded')
       OR position('Furniture' IN a.summary) > 0 OR position('Apparel' IN a.summary) > 0)
UNION ALL
SELECT min(a.id), min((a.created_at AT TIME ZONE 'America/New_York')::time(3))::text || ' .. ' || max((a.created_at AT TIME ZONE 'America/New_York')::time(3))::text,
       'ticker_revalidated_out x' || count(*), 'from ' || chr(39) || 'Commercial, Office & Home Furniture ...' || chr(39) || ' by validation: ' || string_agg(split_part(a.summary, ' ', 1), ',' ORDER BY a.id)
FROM mi_audit_log a
WHERE (a.created_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-15' AND a.event_type = 'ticker_revalidated_out'
  AND position('Commercial, Office & Home Furniture' IN a.summary) > 0
ORDER BY 1;

\echo == D3. ROW (d) every stripped name plus the old apparel roster: where it sat on 10-14, where it sits at the latest night

WITH nights AS (SELECT DISTINCT theme_date AS d FROM mi_themes WHERE theme_date >= DATE '2026-10-08'),
rm AS (
  SELECT DISTINCT split_part(a.summary, ' ', 1) AS tk FROM mi_audit_log a
  WHERE a.event_type = 'ticker_revalidated_out' AND (a.created_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-15'
    AND position('Commercial, Office & Home Furniture' IN a.summary) > 0),
old_ap AS (SELECT unnest(tickers) AS tk FROM mi_themes WHERE name = 'U.S. Apparel & Fashion Recovery' AND theme_date = DATE '2026-10-14' AND stage <> 'Retired'),
pool AS (SELECT tk, true AS stripped FROM rm UNION SELECT tk, false FROM old_ap WHERE tk NOT IN (SELECT tk FROM rm)),
lat AS (SELECT max(d) AS d FROM nights)
SELECT p.tk, p.stripped AS stripped_from_furniture_10_15,
       COALESCE((SELECT string_agg(t.name || ' [' || cardinality(t.tickers) || ']', '; ' ORDER BY t.name) FROM mi_themes t
                 WHERE t.theme_date = DATE '2026-10-14' AND t.stage <> 'Retired' AND p.tk = ANY (t.tickers)), '-- none --') AS sat_in_10_14,
       COALESCE((SELECT string_agg(t.name || ' [' || cardinality(t.tickers) || ']', '; ' ORDER BY t.name) FROM mi_themes t
                 WHERE t.theme_date = lat.d AND t.stage <> 'Retired' AND p.tk = ANY (t.tickers)), '-- none --') AS sits_in_at_latest_night
FROM pool p CROSS JOIN lat ORDER BY p.stripped DESC, p.tk;

\echo == D3b. ROW (d) the stripped names in one line (how many are in no theme now)

WITH nights AS (SELECT DISTINCT theme_date AS d FROM mi_themes WHERE theme_date >= DATE '2026-10-08'),
rm AS (
  SELECT DISTINCT split_part(a.summary, ' ', 1) AS tk FROM mi_audit_log a
  WHERE a.event_type = 'ticker_revalidated_out' AND (a.created_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-15'
    AND position('Commercial, Office & Home Furniture' IN a.summary) > 0),
lat AS (SELECT max(d) AS d FROM nights)
SELECT count(*) AS stripped_names,
       count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM mi_themes t WHERE t.theme_date = lat.d AND t.stage <> 'Retired' AND rm.tk = ANY (t.tickers))) AS in_no_theme_at_latest_night,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM mi_themes t WHERE t.theme_date = lat.d AND t.stage <> 'Retired' AND rm.tk = ANY (t.tickers))) AS in_some_theme_at_latest_night,
       count(*) FILTER (WHERE (SELECT count(*) FROM mi_themes t WHERE t.theme_date = lat.d AND t.stage <> 'Retired' AND rm.tk = ANY (t.tickers)) >= 2) AS in_two_or_more_themes
FROM rm CROSS JOIN lat GROUP BY lat.d;

\echo == D4. ROW (d) BASE RATE per tripwire event since 08-26: did the rename arm act, or did a strip go ahead (weekday column: the rename arm is the Mon/Wed/Fri rescore caller)

WITH tw AS (
  SELECT a.id, a.created_at AS ts, (a.created_at AT TIME ZONE 'America/New_York')::date AS d,
         substring(a.summary FROM '^''(.*?)'': validation flagged') AS th,
         substring(a.summary FROM 'flagged ([0-9]+)/') AS flagged, substring(a.summary FROM 'flagged [0-9]+/([0-9]+)') AS members
  FROM mi_audit_log a WHERE a.event_type = 'validation_mass_removal_name_suspect' AND a.created_at >= TIMESTAMPTZ '2026-08-26'),
x AS (
  SELECT tw.*,
         (SELECT count(*) FROM mi_audit_log r WHERE r.event_type = 'ticker_revalidated_out'
            AND r.summary LIKE '% removed from ' || chr(39) || replace(replace(tw.th, '%', '!%'), '_', '!_') || chr(39) || ' by validation' ESCAPE '!'
            AND r.created_at BETWEEN tw.ts AND tw.ts + interval '2 minutes') AS stripped_within_2_min,
         (SELECT count(*) FROM mi_audit_log r WHERE r.event_type = 'theme_renamed_on_mass_flag'
            AND starts_with(r.summary, chr(39) || tw.th || chr(39) || ' renamed to')
            AND r.created_at BETWEEN tw.ts - interval '2 minutes' AND tw.ts + interval '2 minutes') AS renamed_around_it
  FROM tw)
SELECT d AS night, th AS theme, flagged || '/' || members AS flagged_of_members, stripped_within_2_min, renamed_around_it,
       CASE WHEN renamed_around_it > 0 THEN 'RENAMED (the #214 arm acted)'
            WHEN stripped_within_2_min > 0 THEN 'STRIPPED (a caller without the rename arm)' ELSE 'neither seen' END AS outcome,
       to_char(d, 'Dy') AS weekday
FROM x ORDER BY d, id;

\echo == D5. ROW (d) BASE RATE total

WITH tw AS (
  SELECT a.id, a.created_at AS ts, substring(a.summary FROM '^''(.*?)'': validation flagged') AS th
  FROM mi_audit_log a WHERE a.event_type = 'validation_mass_removal_name_suspect' AND a.created_at >= TIMESTAMPTZ '2026-08-26'),
x AS (
  SELECT tw.id,
         (SELECT count(*) FROM mi_audit_log r WHERE r.event_type = 'theme_renamed_on_mass_flag'
            AND starts_with(r.summary, chr(39) || tw.th || chr(39) || ' renamed to')
            AND r.created_at BETWEEN tw.ts - interval '2 minutes' AND tw.ts + interval '2 minutes') AS ren,
         (SELECT count(*) FROM mi_audit_log r WHERE r.event_type = 'ticker_revalidated_out'
            AND r.summary LIKE '% removed from ' || chr(39) || replace(replace(tw.th, '%', '!%'), '_', '!_') || chr(39) || ' by validation' ESCAPE '!'
            AND r.created_at BETWEEN tw.ts AND tw.ts + interval '2 minutes') AS strp
  FROM tw)
SELECT count(*) AS tripwire_events_since_08_26, count(*) FILTER (WHERE ren > 0) AS ended_in_rename,
       count(*) FILTER (WHERE ren = 0 AND strp > 0) AS ended_in_strip, count(*) FILTER (WHERE ren = 0 AND strp = 0) AS neither_seen
FROM x;

COMMIT;
