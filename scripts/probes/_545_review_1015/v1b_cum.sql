SET default_transaction_read_only = on;
\pset pager off
\echo == C1. cumulative 025-trail-settled ep_low_reclaim rows (live + voided) by ET settle date, fire_date>=09-02 guard, and the live/voided/first split
WITH u AS (
  SELECT 'live' AS tbl, reentry_shape, fire_date, settled_at_025 FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND realized_r_trail_025 IS NOT NULL
  UNION ALL
  SELECT 'voided', reentry_shape, fire_date, settled_at_025 FROM mi_delayed_entry_trigger_voided_0901 WHERE rung='ep_low_reclaim' AND realized_r_trail_025 IS NOT NULL
), d AS (
  SELECT (settled_at_025 AT TIME ZONE 'America/New_York')::date AS sd,
         COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02') AS g,
         COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND tbl='voided') AS voided_g,
         COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND tbl='live' AND reentry_shape='first') AS live_first,
         COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND tbl='live' AND reentry_shape<>'first') AS live_reentry
  FROM u GROUP BY 1
)
SELECT sd, g, SUM(g) OVER (ORDER BY sd) AS cum_guarded, SUM(voided_g) OVER (ORDER BY sd) AS cum_voided, SUM(live_first) OVER (ORDER BY sd) AS cum_live_first, SUM(live_reentry) OVER (ORDER BY sd) AS cum_live_reentry
FROM d WHERE sd <= DATE '2026-09-22' ORDER BY sd;
\echo == C2. by 09-18 17:00 ET cutoff (before that evening's settle run) and by 09-18 end
WITH u AS (
  SELECT 'live' AS tbl, reentry_shape, fire_date, settled_at_025 FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND realized_r_trail_025 IS NOT NULL
  UNION ALL
  SELECT 'voided', reentry_shape, fire_date, settled_at_025 FROM mi_delayed_entry_trigger_voided_0901 WHERE rung='ep_low_reclaim' AND realized_r_trail_025 IS NOT NULL
)
SELECT COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND settled_at_025 < TIMESTAMPTZ '2026-09-18 17:00 America/New_York') AS pre_0918_1700,
       COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND settled_at_025 < TIMESTAMPTZ '2026-09-19 00:00 America/New_York') AS by_0918_end,
       COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND settled_at_025 < TIMESTAMPTZ '2026-09-19 17:00 America/New_York') AS pre_0919_1700
FROM u;
