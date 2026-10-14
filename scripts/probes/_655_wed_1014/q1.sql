-- #655 Wed 2026-10-14 night (night 3 of 5 for the G3 fold DONE-WHEN). READ-ONLY. Window >= 16:30 ET Wed 10-14.
\pset format unaligned
\pset fieldsep '\t'
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et;
\echo == A. theme-related audit events since 16:30 ET Wed (counts)
SELECT event_type, count(*) n, min((created_at AT TIME ZONE 'America/New_York')::time(0))::text first_t, max((created_at AT TIME ZONE 'America/New_York')::time(0))::text last_t
FROM mi_audit_log WHERE created_at >= '2026-10-14 16:30:00-04' AND (event_type LIKE 'theme%' OR event_type LIKE '%fold%')
GROUP BY 1 ORDER BY 3,1;
\echo == A2. theme-engine job runs today
SELECT id, job_id, (started_at AT TIME ZONE 'America/New_York')::text st, status, rows_written, left(coalesce(error_message,''),200) err
FROM mi_job_runs WHERE started_at >= '2026-10-14 12:00:00-04' AND (job_id ILIKE '%theme%' OR job_id ILIKE '%audit%' OR job_id ILIKE '%correct%') ORDER BY id;
\echo == B. theme_small_fold_ran / error (full)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, event_type, summary, detail
FROM mi_audit_log WHERE event_type IN ('theme_small_fold_ran','theme_small_fold_error') AND created_at >= '2026-10-14 16:30:00-04' ORDER BY id;
\echo == C. theme_small_folded rows (summary + key fields)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, summary,
 detail::json->>'theme' th, detail::json->>'home' home, detail::json->>'e_code' e, detail::json->>'members' members, detail::json->>'moved' moved, detail::json->>'released' released, detail::json->>'g3' g3
FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-14 16:30:00-04' ORDER BY id;
\echo == D. theme_correctness_check rows 10-05 on (summary)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, summary
FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-05' ORDER BY id;
\echo == E. sector-cap rows tonight (summaries)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, event_type, summary
FROM mi_audit_log WHERE event_type LIKE 'theme_sector_cap%' AND created_at >= '2026-10-14 16:30:00-04' ORDER BY id;
\echo == E2. kept_distinct detail tonight
SELECT id, detail FROM mi_audit_log WHERE event_type='theme_sector_cap_kept_distinct' AND created_at >= '2026-10-14 16:30:00-04' ORDER BY id;
\echo == G. rule B rows tonight
SELECT id, detail::json->>'theme' th, detail::json->>'members' m, detail::json->>'prior_members' prior
FROM mi_audit_log WHERE event_type='theme_retired_small_fading' AND created_at >= '2026-10-14 16:30:00-04' ORDER BY id;
\echo == H. board by night: n themes, 2-3 members, <=1, retired
SELECT theme_date, count(*) FILTER (WHERE stage<>'Retired') active, count(*) FILTER (WHERE stage<>'Retired' AND array_length(tickers,1) BETWEEN 2 AND 3) n23,
       count(*) FILTER (WHERE stage<>'Retired' AND coalesce(array_length(tickers,1),0) <= 1) n01, count(*) FILTER (WHERE stage='Retired') retired
FROM mi_themes WHERE theme_date >= '2026-10-08' GROUP BY 1 ORDER BY 1;
