\pset pager off
\echo == C1. cumulative 075-trail-settled ep_low_reclaim rows (live + voided), by ET settle date: with and without the fire_date guard
WITH u AS (
  SELECT 'live' AS tbl, reentry_shape, fire_date, settled_at_075 FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND realized_r_trail_075 IS NOT NULL
  UNION ALL
  SELECT 'voided', reentry_shape, fire_date, settled_at_075 FROM mi_delayed_entry_trigger_voided_0901 WHERE rung='ep_low_reclaim' AND realized_r_trail_075 IS NOT NULL
), d AS (
  SELECT (settled_at_075 AT TIME ZONE 'America/New_York')::date AS sd,
         COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02') AS g,
         COUNT(*) AS ng,
         COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND tbl='live' AND reentry_shape='first') AS live_first,
         COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND tbl='voided') AS voided_g
  FROM u GROUP BY 1
)
SELECT sd, g, SUM(g) OVER (ORDER BY sd) AS cum_guarded, SUM(ng) OVER (ORDER BY sd) AS cum_unguarded,
       SUM(live_first) OVER (ORDER BY sd) AS cum_live_first, SUM(voided_g) OVER (ORDER BY sd) AS cum_voided
FROM d WHERE sd <= DATE '2026-09-30' ORDER BY sd;
\echo == C2. any settled_at_075 NULL while realized set (stamp missing)?
SELECT COUNT(*) FROM mi_delayed_entry_trigger WHERE realized_r_trail_075 IS NOT NULL AND settled_at_075 IS NULL;
\echo == W1. QCOM daily bars 2026-08-01..10-13
SELECT trade_date, high_price, low_price, close FROM mi_daily_closes WHERE ticker='QCOM' AND trade_date BETWEEN DATE '2026-08-01' AND DATE '2026-10-13' ORDER BY trade_date;
\echo == W2. CRWD daily bars 2026-07-25..10-13
SELECT trade_date, high_price, low_price, close FROM mi_daily_closes WHERE ticker='CRWD' AND trade_date BETWEEN DATE '2026-07-25' AND DATE '2026-10-13' ORDER BY trade_date;
\echo == W3. the two rows' stored day-0 fields + checkpoints
SELECT id, ticker, fire_date, fire_minute_et, entry_price, stop_price, stop_price_075, stop_price_100, day_high, day_low, day_close, day0_post_low, day0_post_high,
       outcome, realized_r, outcome_trail, realized_r_trail, outcome_075, realized_r_075, outcome_trail_075, realized_r_trail_075, mfe_r_075, mae_r_075,
       outcome_100, realized_r_100, outcome_trail_100, realized_r_trail_100, mfe_r_100
FROM mi_delayed_entry_trigger WHERE id IN (3305, 2670);
