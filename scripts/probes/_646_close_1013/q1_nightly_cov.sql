-- NOTE: 1st run used an upper bound of UTC midnight 2026-10-13 (=20:00 ET 10-12) and so missed Mon 10-12's 21:00/21:10 ET rows; bound corrected to 2026-10-13 12:00 UTC and re-run (this .out is the corrected one).
\pset pager off
\pset null '-'
-- One row per trading night (Mon-Fri, 2026-09-14..2026-10-12 ET). For each of the three coverage slots:
-- n = rows landed that ET day, t = ET time of first row, ex/cov/gap/fail/def = fields parsed from the row's own JSON detail.
WITH days AS (
  SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d) < 6
), cov AS (
  SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type,
         (created_at AT TIME ZONE 'America/New_York')::time(0) AS t, detail::jsonb AS j
  FROM mi_audit_log
  WHERE event_type IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening')
    AND created_at >= '2026-09-14' AND created_at < '2026-10-13 12:00+00'
), s AS (
  SELECT d, event_type, count(*) AS n, min(t) AS t,
         max((j->>'examined')::int) AS ex, max((j->>'covered')::int) AS cov,
         max(jsonb_array_length(j->'gaps')) AS gap, max(jsonb_array_length(j->'check_failed')) AS fail, max(jsonb_array_length(j->'deferred')) AS def
  FROM cov GROUP BY 1,2
)
SELECT days.d, to_char(days.d,'Dy') AS dow,
  p.n AS pc_n, p.t AS pc_t, p.ex AS pc_ex, p.cov AS pc_cov, p.gap AS pc_gap, p.fail AS pc_fail, p.def AS pc_def,
  l.n AS lt_n, l.t AS lt_t, l.ex AS lt_ex, l.cov AS lt_cov, l.gap AS lt_gap, l.fail AS lt_fail, l.def AS lt_def,
  e.n AS ev_n, e.t AS ev_t, e.ex AS ev_ex, e.cov AS ev_cov, e.gap AS ev_gap, e.fail AS ev_fail, e.def AS ev_def
FROM days
LEFT JOIN s p ON p.d=days.d AND p.event_type='coverage_checked_post_close'
LEFT JOIN s l ON l.d=days.d AND l.event_type='coverage_checked_late'
LEFT JOIN s e ON e.d=days.d AND e.event_type='coverage_verified_evening'
ORDER BY days.d;

-- Totals + anything outside Mon-Fri / outside the window
SELECT event_type, count(*) AS rows, count(DISTINCT (created_at AT TIME ZONE 'America/New_York')::date) AS distinct_days,
       sum((detail::jsonb->>'examined')::int) AS sum_examined, sum((detail::jsonb->>'covered')::int) AS sum_covered,
       sum(jsonb_array_length(detail::jsonb->'gaps')) AS sum_gaps, sum(jsonb_array_length(detail::jsonb->'check_failed')) AS sum_failed,
       sum(jsonb_array_length(detail::jsonb->'deferred')) AS sum_deferred,
       count(*) FILTER (WHERE (detail::jsonb->>'examined')::int = 0) AS rows_examined_zero,
       count(*) FILTER (WHERE (detail::jsonb->>'examined')::int > 0) AS rows_examined_pos
FROM mi_audit_log
WHERE event_type IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening')
  AND created_at >= '2026-09-12' AND created_at < '2026-10-13 14:00+00'
GROUP BY 1 ORDER BY 1;

-- Any such row outside the Mon-Fri 2026-09-14..10-12 list (weekend / duplicate / stray)?
SELECT id, event_type, created_at AT TIME ZONE 'America/New_York' AS et, to_char(created_at AT TIME ZONE 'America/New_York','Dy') AS dow
FROM mi_audit_log
WHERE event_type IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening')
  AND created_at >= '2026-09-12' AND created_at < '2026-10-13 14:00+00'
  AND (extract(isodow FROM created_at AT TIME ZONE 'America/New_York') >= 6 OR (created_at AT TIME ZONE 'America/New_York')::date NOT BETWEEN '2026-09-14' AND '2026-10-12');
