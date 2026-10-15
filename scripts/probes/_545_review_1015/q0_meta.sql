SET default_transaction_read_only = on;
\pset pager off
\echo == now
SELECT now() AT TIME ZONE 'America/New_York' AS now_et;
\echo == calendar: SPY last bar and sessions since 09-01 (maturity clock)
SELECT MAX(trade_date) AS last_spy_bar, COUNT(*) FILTER (WHERE trade_date >= DATE '2026-09-01') AS spy_sessions_since_0901 FROM mi_daily_closes WHERE ticker='SPY';
SELECT string_agg(to_char(trade_date,'MM-DD'), ' ' ORDER BY trade_date) AS spy_sessions_0901_on FROM mi_daily_closes WHERE ticker='SPY' AND trade_date>=DATE '2026-09-01';
\echo == 025 columns present (live + voided)
SELECT table_name, COUNT(*) AS n_025_cols FROM information_schema.columns WHERE table_name IN ('mi_delayed_entry_trigger','mi_delayed_entry_trigger_voided_0901') AND column_name LIKE '%\_025' GROUP BY 1 ORDER BY 1;
\echo == 025 stop recorded on which rows? (post-09-02 live rows: adr basis present vs stop_price_025 present)
SELECT fire_date >= DATE '2026-09-02' AS prospective, COUNT(*) AS n, COUNT(ep_adr20_n) AS has_adr, COUNT(stop_price_025) AS has_stop025, COUNT(outcome_025) AS has_outcome025, COUNT(realized_r_trail_025) AS has_trail025
FROM mi_delayed_entry_trigger GROUP BY 1 ORDER BY 1;
\echo == 025 stop recorded on the 09-02 fire date itself (did the 025 columns ship before that day's fires?)
SELECT id, ticker, rung, reentry_shape, fire_date, ep_adr20_n, stop_price_025 IS NOT NULL AS has_stop025, stop_price_075 IS NOT NULL AS has_stop075, (created_at AT TIME ZONE 'America/New_York') AS created_et
FROM mi_delayed_entry_trigger WHERE fire_date <= DATE '2026-09-03' ORDER BY fire_date, id;
\echo == THE PREDICATE AS WRITTEN IN YAML (live table)
SELECT CASE WHEN to_regclass('mi_delayed_entry_trigger') IS NULL THEN 0
            ELSE (SELECT COUNT(*) FROM mi_delayed_entry_trigger
                  WHERE rung = 'ep_low_reclaim' AND fire_date >= DATE '2026-09-02' AND realized_r_trail_025 IS NOT NULL) END AS predicate_as_written;
\echo == predicate_as_written split by shape and by 20-session maturity (SPY clock)
SELECT t.reentry_shape,
       COUNT(*) AS counted_by_predicate,
       COUNT(*) FILTER (WHERE (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker='SPY' AND d.trade_date > t.fire_date) >= 20) AS mature20,
       COUNT(*) FILTER (WHERE (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker='SPY' AND d.trade_date > t.fire_date) < 20) AS immature,
       COUNT(*) FILTER (WHERE t.outcome_trail_025 = 'stop' AND (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker='SPY' AND d.trade_date > t.fire_date) < 20) AS immature_stopouts
FROM mi_delayed_entry_trigger t
WHERE t.rung='ep_low_reclaim' AND t.fire_date >= DATE '2026-09-02' AND t.realized_r_trail_025 IS NOT NULL
GROUP BY 1 ORDER BY 1;
\echo == voided table: the old pre-void cohort the 09-19 reading '111' could have counted
SELECT to_regclass('mi_delayed_entry_trigger_voided_0901') IS NOT NULL AS voided_table_exists;
SELECT reentry_shape, COUNT(*) AS n, COUNT(realized_r_trail_025) AS settled_025,
       COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND realized_r_trail_025 IS NOT NULL) AS guarded_settled_025
FROM mi_delayed_entry_trigger_voided_0901 WHERE rung='ep_low_reclaim' GROUP BY 1 ORDER BY 1;
\echo == candidate corrected predicate A (first attempts, incumbent + 025 + 075 trail arms settled, 20 SPY sessions elapsed)
SELECT CASE WHEN to_regclass('mi_delayed_entry_trigger') IS NULL THEN 0
            ELSE (SELECT COUNT(*) FROM mi_delayed_entry_trigger t
                  WHERE t.rung = 'ep_low_reclaim' AND t.reentry_shape = 'first'
                    AND t.fire_date >= DATE '2026-09-02'
                    AND t.realized_r_trail IS NOT NULL AND t.realized_r_trail_025 IS NOT NULL
                    AND t.realized_r_trail_075 IS NOT NULL
                    AND (SELECT COUNT(*) FROM mi_daily_closes d
                         WHERE d.ticker = 'SPY' AND d.trade_date > t.fire_date) >= 20) END AS corrected_A_3arms;
\echo == candidate B (first attempts, incumbent + 025 only, 20 sessions) - how much the 075 requirement costs
SELECT COUNT(*) AS corrected_B_025_and_incumbent_only FROM mi_delayed_entry_trigger t
WHERE t.rung = 'ep_low_reclaim' AND t.reentry_shape = 'first' AND t.fire_date >= DATE '2026-09-02'
  AND t.realized_r_trail IS NOT NULL AND t.realized_r_trail_025 IS NOT NULL
  AND (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker = 'SPY' AND d.trade_date > t.fire_date) >= 20;
\echo == do trail and none arms of 025 settle together? (any row with one set and the other null)
SELECT COUNT(*) FILTER (WHERE (realized_r_trail_025 IS NULL) <> (realized_r_025 IS NULL)) AS trail_none_mismatch_025,
       COUNT(*) FILTER (WHERE (realized_r_trail_075 IS NULL) <> (realized_r_075 IS NULL)) AS trail_none_mismatch_075,
       COUNT(*) FILTER (WHERE (outcome_025 = 'unscoreable') AND realized_r_trail_025 IS NOT NULL) AS unsc_but_r_025
FROM mi_delayed_entry_trigger WHERE fire_date >= DATE '2026-09-02';
