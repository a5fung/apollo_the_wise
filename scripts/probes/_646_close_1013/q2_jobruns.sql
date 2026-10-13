-- NOTE: 1st run used an upper bound of UTC midnight 2026-10-13 (=20:00 ET 10-12) and so missed Mon 10-12's 21:00/21:10 ET rows; bound corrected to 2026-10-13 12:00 UTC and re-run (this .out is the corrected one).
\pset pager off
\pset null '-'
-- job id census (anything resembling the named jobs) for the window
SELECT job_id, count(*) AS runs, count(*) FILTER (WHERE status='success') AS success, count(*) FILTER (WHERE status<>'success') AS non_success,
       min(started_at AT TIME ZONE 'America/New_York')::time(0) AS min_t_et, max(started_at AT TIME ZONE 'America/New_York')::time(0) AS max_t_et,
       min((started_at AT TIME ZONE 'America/New_York')::date) AS first_day, max((started_at AT TIME ZONE 'America/New_York')::date) AS last_day
FROM mi_job_runs
WHERE started_at >= '2026-09-12' AND started_at < '2026-10-13 14:00+00'
  AND job_id ~* '(coverage|backstop|eod_cleanup|live_position_update|stop_|naked|post_close|position)'
GROUP BY 1 ORDER BY 1;

-- per night, per named job: status(es) and start time ET
WITH days AS (
  SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d) < 6
), r AS (
  SELECT (started_at AT TIME ZONE 'America/New_York')::date AS d, job_id, status, (started_at AT TIME ZONE 'America/New_York')::time(0) AS t, rows_written, error_message
  FROM mi_job_runs
  WHERE started_at >= '2026-09-14' AND started_at < '2026-10-13 12:00+00'
    AND job_id IN ('coverage_watch_post_close','coverage_watch_late','coverage_watch_evening','evening_position_backstop','eod_cleanup','live_position_update','post_close_stop_refresh')
), a AS (
  SELECT d, job_id, count(*) AS n, string_agg(status,',' ORDER BY t) AS st, min(t) AS t FROM r GROUP BY 1,2
)
SELECT days.d, to_char(days.d,'Dy') AS dow,
  eod.st AS eod_st, eod.t AS eod_t,
  pcs.st AS refresh_st, pcs.t AS refresh_t,
  lpu.st AS lpu_st, lpu.t AS lpu_t,
  c1.st AS cw_pc_st, c1.t AS cw_pc_t,
  c2.st AS cw_late_st, c2.t AS cw_late_t,
  eb.st AS backstop_st, eb.t AS backstop_t,
  c3.st AS cw_ev_st, c3.t AS cw_ev_t
FROM days
LEFT JOIN a eod ON eod.d=days.d AND eod.job_id='eod_cleanup'
LEFT JOIN a pcs ON pcs.d=days.d AND pcs.job_id='post_close_stop_refresh'
LEFT JOIN a lpu ON lpu.d=days.d AND lpu.job_id='live_position_update'
LEFT JOIN a c1 ON c1.d=days.d AND c1.job_id='coverage_watch_post_close'
LEFT JOIN a c2 ON c2.d=days.d AND c2.job_id='coverage_watch_late'
LEFT JOIN a eb ON eb.d=days.d AND eb.job_id='evening_position_backstop'
LEFT JOIN a c3 ON c3.d=days.d AND c3.job_id='coverage_watch_evening'
ORDER BY days.d;

-- every non-success run of ANY of the named/regex jobs in the window, with error text
SELECT started_at AT TIME ZONE 'America/New_York' AS started_et, scheduled_for AT TIME ZONE 'America/New_York' AS sched_et, job_id, status, left(coalesce(error_message,''),200) AS err
FROM mi_job_runs
WHERE started_at >= '2026-09-12' AND started_at < '2026-10-13 14:00+00' AND status <> 'success'
  AND job_id ~* '(coverage|backstop|eod_cleanup|live_position_update|stop_|naked|post_close|position)'
ORDER BY started_at;

-- ALL non-success runs of any job in the window (37 expected) so a hit on our jobs by another id is visible
SELECT started_at AT TIME ZONE 'America/New_York' AS started_et, job_id, status, left(coalesce(error_message,''),120) AS err
FROM mi_job_runs WHERE started_at >= '2026-09-12' AND started_at < '2026-10-13 14:00+00' AND status <> 'success' ORDER BY started_at;
