-- #655 Wed 2026-10-14 night, part 4 (explain the undone folds + parent-pass link yield). READ-ONLY.
\pset format unaligned
\pset fieldsep '\t'
\echo == 1. theme_member_rehomed rows tonight
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, left(summary,260) s FROM mi_audit_log WHERE event_type='theme_member_rehomed' AND created_at >= '2026-10-14 16:30:00-04' ORDER BY id;
\echo == 2. audit rows tonight naming BOX or DBX (summary only)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, event_type, left(summary,240) s FROM mi_audit_log
WHERE created_at >= '2026-10-14 16:30:00-04' AND created_at < '2026-10-14 18:30:00-04' AND (summary ~ '(^|[^A-Z])(BOX|DBX)([^A-Z]|$)') ORDER BY id;
\echo == 3. parent pass ran summaries 10-12 on
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, left(summary,260) s FROM mi_audit_log WHERE event_type='theme_parent_pass_ran' AND created_at >= '2026-10-12' ORDER BY id;
\echo == 3b. parent pass per-night verdict counts (linked or CHILD_OF vs distinct)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) FROM mi_audit_log WHERE event_type LIKE 'theme_parent_pass%' AND created_at >= '2026-10-08' GROUP BY 1,2 ORDER BY 1,2;
\echo == 4. shadow_themes_promoted summaries 10-12 on
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, left(summary,260) s FROM mi_audit_log WHERE event_type='shadow_themes_promoted' AND created_at >= '2026-10-12' ORDER BY id;
\echo == 4b. promote-lane rows per night: all shadow_promoted rows 2-3 members active vs total, by theme_date
SELECT theme_date, count(*) FILTER (WHERE source='shadow_promoted' AND stage<>'Retired') promoted_active,
 count(*) FILTER (WHERE source='shadow_promoted' AND stage<>'Retired' AND array_length(tickers,1) BETWEEN 2 AND 3) promoted_small
FROM mi_themes WHERE theme_date >= '2026-10-08' GROUP BY 1 ORDER BY 1;
\echo == 4c. promote-lane names tonight that had a Retired tombstone or small active row on the prior board (re-mint of a dissolved name)
SELECT t.name, array_length(t.tickers,1) n, array_to_string(t.tickers,',') tk,
 (SELECT string_agg(p.theme_date::text || ':' || p.stage || ':' || coalesce(array_length(p.tickers,1),0)::text, ' ' ORDER BY p.theme_date) FROM mi_themes p WHERE p.name=t.name AND p.theme_date >= '2026-10-09' AND p.theme_date < '2026-10-14') prior_rows
FROM mi_themes t WHERE t.theme_date='2026-10-14' AND t.source='shadow_promoted' AND t.stage<>'Retired' ORDER BY 1;
