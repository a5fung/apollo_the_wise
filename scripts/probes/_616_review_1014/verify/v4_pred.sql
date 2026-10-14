\pset pager off
\echo == proposed tightened predicate (first attempts, all three trail arms settled, 20 SPY sessions elapsed since fire)
SELECT CASE WHEN to_regclass('mi_delayed_entry_trigger') IS NULL THEN 0 ELSE (SELECT COUNT(*) FROM mi_delayed_entry_trigger t WHERE t.rung = 'ep_low_reclaim' AND t.reentry_shape = 'first' AND t.fire_date >= DATE '2026-09-02' AND t.realized_r_trail IS NOT NULL AND t.realized_r_trail_075 IS NOT NULL AND t.realized_r_trail_100 IS NOT NULL AND (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker = 'SPY' AND d.trade_date > t.fire_date) >= 20) END AS tightened_predicate;
\echo == current predicate as written
SELECT CASE WHEN to_regclass('mi_delayed_entry_trigger') IS NULL THEN 0 ELSE (SELECT COUNT(*) FROM mi_delayed_entry_trigger WHERE rung = 'ep_low_reclaim' AND fire_date >= DATE '2026-09-02' AND realized_r_trail_075 IS NOT NULL) END AS current_predicate;
