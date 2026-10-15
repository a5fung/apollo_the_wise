SET default_transaction_read_only = on;
\pset pager off
\echo == R1. what the 09-19 reading of 111 counted: ep_low_reclaim rows settled on the 025 trail arm by end of 09-19 ET, by table and shape (fire_date >= 09-02 guard)
WITH u AS (
  SELECT 'live' AS tbl, reentry_shape, fire_date, settled_at_025, realized_r_trail_025 FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim'
  UNION ALL
  SELECT 'voided', reentry_shape, fire_date, settled_at_025, realized_r_trail_025 FROM mi_delayed_entry_trigger_voided_0901 WHERE rung='ep_low_reclaim'
)
SELECT tbl, reentry_shape,
  COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND realized_r_trail_025 IS NOT NULL AND settled_at_025 < TIMESTAMPTZ '2026-09-20 00:00 America/New_York') AS by_0919_end_guarded,
  COUNT(*) FILTER (WHERE realized_r_trail_025 IS NOT NULL AND settled_at_025 < TIMESTAMPTZ '2026-09-20 00:00 America/New_York') AS by_0919_end_unguarded,
  COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND realized_r_trail_025 IS NOT NULL) AS settled_now_guarded
FROM u GROUP BY 1,2 ORDER BY 1,2;
\echo == R2. missing settle stamps?
SELECT COUNT(*) AS r_set_but_no_settled_at_025 FROM mi_delayed_entry_trigger WHERE realized_r_trail_025 IS NOT NULL AND settled_at_025 IS NULL;
\echo == R3. latest settle stamps (did the 10-14 EOD settle run?)
SELECT MAX(settled_at AT TIME ZONE 'America/New_York') AS last_inc_settle_et, MAX(settled_at_025 AT TIME ZONE 'America/New_York') AS last_025_settle_et, MAX(created_at AT TIME ZONE 'America/New_York') AS last_create_et FROM mi_delayed_entry_trigger;
