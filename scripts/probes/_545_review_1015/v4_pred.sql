SET default_transaction_read_only = on;
\pset pager off
\echo == corrected predicate, exact proposed YAML text (expect 6 on 2026-10-15)
SELECT CASE WHEN to_regclass('mi_delayed_entry_trigger') IS NULL THEN 0
                  ELSE (SELECT COUNT(*) FROM mi_delayed_entry_trigger t
                        WHERE t.rung = 'ep_low_reclaim' AND t.reentry_shape = 'first'
                          AND t.fire_date >= DATE '2026-09-02'
                          AND t.realized_r_trail IS NOT NULL AND t.realized_r_trail_025 IS NOT NULL
                          AND t.realized_r_trail_075 IS NOT NULL
                          AND (SELECT COUNT(*) FROM mi_daily_closes d
                               WHERE d.ticker = 'SPY' AND d.trade_date > t.fire_date) >= 20) END AS corrected_predicate;
\echo == predicate as currently written in YAML (expect 30)
SELECT CASE WHEN to_regclass('mi_delayed_entry_trigger') IS NULL THEN 0
                  ELSE (SELECT COUNT(*) FROM mi_delayed_entry_trigger
                        WHERE rung = 'ep_low_reclaim'
                          AND fire_date >= DATE '2026-09-02'
                          AND realized_r_trail_025 IS NOT NULL) END AS predicate_as_written;
