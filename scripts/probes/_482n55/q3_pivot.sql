SELECT account_mode,
       count(*) AS n,
       min(alert_date)::text AS first, max(alert_date)::text AS last,
       sum(CASE WHEN abstained THEN 1 ELSE 0 END) AS abstained_n,
       round(avg(baseline_exit_r)::numeric,2) AS base_avg,
       round(avg(p1_exit_r)::numeric,2) AS p1_avg,
       round(avg(p2_exit_r)::numeric,2) AS p2_avg
FROM mi_pivot_stop_shadow GROUP BY account_mode;
SELECT count(*) AS era_c_rows FROM mi_pivot_stop_shadow WHERE alert_date >= '2026-08-16' AND NOT abstained;
