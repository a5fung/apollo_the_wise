-- #655 Mon 2026-10-12 evening verify. READ-ONLY. Window: tonight's engine run (>= 16:30 ET Mon 10-12).
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et;
\echo == A. theme-related audit events since 16:30 ET (counts)
SELECT event_type, count(*) n, min((created_at AT TIME ZONE 'America/New_York')::time(0))::text first_t, max((created_at AT TIME ZONE 'America/New_York')::time(0))::text last_t
FROM mi_audit_log WHERE created_at >= '2026-10-12 16:30:00-04' AND (event_type LIKE 'theme%' OR event_type LIKE '%fold%')
GROUP BY 1 ORDER BY 3,1;
\echo == B. theme_small_fold_ran / error (full)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, event_type, summary, detail
FROM mi_audit_log WHERE event_type IN ('theme_small_fold_ran','theme_small_fold_error') AND created_at >= '2026-10-12 16:30:00-04' ORDER BY id;
\echo == C. theme_small_folded rows (full)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, summary, detail
FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12 16:30:00-04' ORDER BY id;
\echo == D. theme_correctness_check rows (last 8 sessions)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::text t, summary
FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-01' ORDER BY id;
\echo == D2. tonight's theme_correctness_check detail
SELECT id, detail FROM mi_audit_log WHERE event_type='theme_correctness_check' AND created_at >= '2026-10-12 16:30:00-04' ORDER BY id;
\echo == E. sector-cap rows tonight (kept_distinct, absorbed, not_absorbed) summaries
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, event_type, summary
FROM mi_audit_log WHERE event_type LIKE 'theme_sector_cap%' AND created_at >= '2026-10-12 16:30:00-04' ORDER BY id;
\echo == E2. kept_distinct detail tonight
SELECT id, detail FROM mi_audit_log WHERE event_type='theme_sector_cap_kept_distinct' AND created_at >= '2026-10-12 16:30:00-04' ORDER BY id;
\echo == F. sector-cap events by night, last 10 days (counts)
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) n
FROM mi_audit_log WHERE event_type LIKE 'theme_sector_cap%' AND created_at >= '2026-10-02' GROUP BY 1,2 ORDER BY 1,2;
\echo == G. rule B rows tonight
SELECT id, summary FROM mi_audit_log WHERE event_type='theme_retired_small_fading' AND created_at >= '2026-10-12 16:30:00-04' ORDER BY id;
\echo == H. board by night: theme_date, stage, count, count 2-3 members, count <=1
SELECT theme_date, count(*) n, count(*) FILTER (WHERE array_length(tickers,1) BETWEEN 2 AND 3) n23, count(*) FILTER (WHERE coalesce(array_length(tickers,1),0) <= 1) n01,
       count(*) FILTER (WHERE stage='Retired') retired
FROM mi_themes WHERE theme_date >= '2026-10-05' GROUP BY 1 ORDER BY 1;
