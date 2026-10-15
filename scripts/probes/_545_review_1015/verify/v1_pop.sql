SET default_transaction_read_only = on;
\pset pager off
\echo == N1. clock: now ET, last SPY bar
SELECT now() AT TIME ZONE 'America/New_York' AS now_et, (SELECT MAX(trade_date) FROM mi_daily_closes WHERE ticker='SPY') AS last_spy_bar;
\echo == N2. predicate EXACTLY as written in the YAML today
SELECT CASE WHEN to_regclass('mi_delayed_entry_trigger') IS NULL THEN 0
            ELSE (SELECT COUNT(*) FROM mi_delayed_entry_trigger
                  WHERE rung = 'ep_low_reclaim'
                    AND fire_date >= DATE '2026-09-02'
                    AND realized_r_trail_025 IS NOT NULL) END AS predicate_as_written;
\echo == N3. what it counts: shape x mature(20 SPY sessions after fire) x 025 trail outcome
SELECT t.reentry_shape,
       ((SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker='SPY' AND d.trade_date > t.fire_date) >= 20) AS mature20,
       t.outcome_trail_025, COUNT(*) AS n
FROM mi_delayed_entry_trigger t
WHERE t.rung='ep_low_reclaim' AND t.fire_date >= DATE '2026-09-02' AND t.realized_r_trail_025 IS NOT NULL
GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo == N4. ep_low_reclaim live rows by shape and prospective flag
SELECT reentry_shape, fire_date >= DATE '2026-09-02' AS prospective, COUNT(*) AS n, MIN(fire_date) AS min_fire, MAX(fire_date) AS max_fire,
       COUNT(DISTINCT (ticker, ep_date)) AS campaigns
FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' GROUP BY 1,2 ORDER BY 1,2;
\echo == N5. ep_low_reclaim first attempts since 09-02 missing a live EP alert (expect 0)
SELECT COUNT(*) AS no_live_ep FROM mi_delayed_entry_trigger t
WHERE t.rung='ep_low_reclaim' AND t.reentry_shape='first' AND t.fire_date >= DATE '2026-09-02'
  AND NOT EXISTS (SELECT 1 FROM mi_ep_alerts a WHERE a.ticker=t.ticker AND a.alert_date=t.ep_date AND COALESCE(a.source,'live')='live');
\echo == N6. proposed corrected predicate (exact text)
SELECT CASE WHEN to_regclass('mi_delayed_entry_trigger') IS NULL THEN 0
            ELSE (SELECT COUNT(*) FROM mi_delayed_entry_trigger t
                  WHERE t.rung = 'ep_low_reclaim' AND t.reentry_shape = 'first'
                    AND t.fire_date >= DATE '2026-09-02'
                    AND t.realized_r_trail IS NOT NULL AND t.realized_r_trail_025 IS NOT NULL
                    AND t.realized_r_trail_075 IS NOT NULL
                    AND (SELECT COUNT(*) FROM mi_daily_closes d
                         WHERE d.ticker = 'SPY' AND d.trade_date > t.fire_date) >= 20) END AS corrected_predicate;
\echo == N7. the 09-19 reading of 111: live + voided ep_low_reclaim rows with 025 trail settled, fire>=09-02, by settle-stamp cutoff
WITH u AS (
  SELECT 'live' AS tbl, reentry_shape, fire_date, settled_at_025 FROM mi_delayed_entry_trigger
   WHERE rung='ep_low_reclaim' AND realized_r_trail_025 IS NOT NULL AND fire_date >= DATE '2026-09-02'
  UNION ALL
  SELECT 'voided', reentry_shape, fire_date, settled_at_025 FROM mi_delayed_entry_trigger_voided_0901
   WHERE rung='ep_low_reclaim' AND realized_r_trail_025 IS NOT NULL AND fire_date >= DATE '2026-09-02'
)
SELECT tbl, reentry_shape,
       COUNT(*) FILTER (WHERE settled_at_025 < TIMESTAMPTZ '2026-09-18 12:00 America/New_York') AS before_0918_noon,
       COUNT(*) FILTER (WHERE settled_at_025 < TIMESTAMPTZ '2026-09-19 12:00 America/New_York') AS before_0919_noon,
       COUNT(*) FILTER (WHERE settled_at_025 < TIMESTAMPTZ '2026-09-20 00:00 America/New_York') AS before_0920
FROM u GROUP BY ROLLUP (1,2) ORDER BY 1,2;
\echo == N8. the settle-run stamps between 09-16 and 09-20 (ET) on ep_low_reclaim 025 trail settlements (live+voided)
WITH u AS (
  SELECT settled_at_025 FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND realized_r_trail_025 IS NOT NULL AND fire_date >= DATE '2026-09-02'
  UNION ALL
  SELECT settled_at_025 FROM mi_delayed_entry_trigger_voided_0901 WHERE rung='ep_low_reclaim' AND realized_r_trail_025 IS NOT NULL AND fire_date >= DATE '2026-09-02'
)
SELECT date_trunc('minute', settled_at_025 AT TIME ZONE 'America/New_York') AS run_et, COUNT(*) FROM u
WHERE settled_at_025 >= TIMESTAMPTZ '2026-09-16 00:00 America/New_York' AND settled_at_025 < TIMESTAMPTZ '2026-09-21 00:00 America/New_York'
GROUP BY 1 ORDER BY 1;
\echo == N9. 025 stop first stamped: earliest created_at of any row carrying stop_price_025 vs the CRWD 09-02 row
SELECT MIN(created_at AT TIME ZONE 'America/New_York') AS first_025_stamp_et FROM mi_delayed_entry_trigger WHERE stop_price_025 IS NOT NULL;
SELECT MIN(created_at AT TIME ZONE 'America/New_York') AS first_025_stamp_voided_et FROM mi_delayed_entry_trigger_voided_0901 WHERE stop_price_025 IS NOT NULL;
SELECT id, ticker, fire_date, created_at AT TIME ZONE 'America/New_York' AS created_et, stop_price_025, outcome_025, outcome_trail_025, settled_at_025 AT TIME ZONE 'America/New_York' AS s025_et
FROM mi_delayed_entry_trigger WHERE id = 2670;
