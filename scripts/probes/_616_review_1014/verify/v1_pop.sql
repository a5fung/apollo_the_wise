\pset pager off
\echo == P1. ep_low_reclaim rows in LIVE table, all shapes, by fire-date bucket
SELECT reentry_shape, (fire_date >= DATE '2026-09-02') AS prospective, COUNT(*) AS n,
       MIN(fire_date), MAX(fire_date)
FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' GROUP BY 1,2 ORDER BY 1,2;
\echo == P2. first attempts since 09-02: one row each, with provenance (created vs fired), live-EP source, own-ticker bar count after fire
SELECT t.id, t.ticker, t.ep_date, t.fire_date, t.fire_minute_et AS fm, t.prior_attempt_id AS pa,
       (t.created_at AT TIME ZONE 'America/New_York')::date AS created_et,
       (t.created_at AT TIME ZONE 'America/New_York')::date - t.fire_date AS lag_days,
       t.pattern_version AS pv, t.screen_version AS sv, t.settle_version AS stv,
       t.settle_version_075 AS s75, t.settle_version_100 AS s100, t.ep_adr20_n AS adrn,
       (SELECT string_agg(DISTINCT COALESCE(a.source,'<null>'), ',') FROM mi_ep_alerts a WHERE a.ticker=t.ticker AND a.alert_date=t.ep_date) AS ep_alert_sources,
       (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker=t.ticker AND d.trade_date > t.fire_date) AS own_bars_after,
       (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker='SPY' AND d.trade_date > t.fire_date) AS spy_bars_after
FROM mi_delayed_entry_trigger t
WHERE t.rung='ep_low_reclaim' AND t.reentry_shape='first' AND t.fire_date >= DATE '2026-09-02'
ORDER BY t.fire_date, t.id;
\echo == P3. distinct campaigns among those first attempts
SELECT COUNT(*) AS rows, COUNT(DISTINCT (ticker, ep_date)) AS campaigns, COUNT(DISTINCT ticker) AS tickers
FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND reentry_shape='first' AND fire_date >= DATE '2026-09-02';
\echo == P4. mi_ep_alerts source values overall (what "live" means)
SELECT COALESCE(source,'<null>') AS source, COUNT(*) FROM mi_ep_alerts WHERE alert_date >= DATE '2026-08-01' GROUP BY 1 ORDER BY 2 DESC;
\echo == P5. predicate as written, today
SELECT COUNT(*) AS predicate_today FROM mi_delayed_entry_trigger
WHERE rung='ep_low_reclaim' AND fire_date >= DATE '2026-09-02' AND realized_r_trail_075 IS NOT NULL;
\echo == R1. reconcile the 09-19 reading of 160: live + voided, settled on the 075 trail arm by 09-19 (two cutoffs), by table and shape
WITH u AS (
  SELECT 'live' AS tbl, reentry_shape, fire_date, settled_at_075, realized_r_trail_075 FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim'
  UNION ALL
  SELECT 'voided', reentry_shape, fire_date, settled_at_075, realized_r_trail_075 FROM mi_delayed_entry_trigger_voided_0901 WHERE rung='ep_low_reclaim'
)
SELECT tbl, reentry_shape,
  COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND realized_r_trail_075 IS NOT NULL AND settled_at_075 < TIMESTAMPTZ '2026-09-19 17:00 America/New_York') AS by_0919_pre_eod,
  COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND realized_r_trail_075 IS NOT NULL AND settled_at_075 < TIMESTAMPTZ '2026-09-20 00:00 America/New_York') AS by_0919_end,
  COUNT(*) FILTER (WHERE fire_date <  DATE '2026-09-02' AND realized_r_trail_075 IS NOT NULL AND settled_at_075 < TIMESTAMPTZ '2026-09-20 00:00 America/New_York') AS pre0902_by_0919_end,
  COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02' AND realized_r_trail_075 IS NOT NULL) AS settled_now
FROM u GROUP BY 1,2 ORDER BY 1,2;
\echo == R2. voided table: ep_low_reclaim since 09-02 by shape, settled/total, latest settle stamp, EP-date range
SELECT reentry_shape, COUNT(*) AS n, COUNT(realized_r_trail_075) AS settled_075,
       MAX(settled_at_075 AT TIME ZONE 'America/New_York') AS last_settle_et, MIN(ep_date), MAX(ep_date)
FROM mi_delayed_entry_trigger_voided_0901 WHERE rung='ep_low_reclaim' AND fire_date >= DATE '2026-09-02' GROUP BY 1 ORDER BY 1;
\echo == R3. live-table settled 075 rows by shape x 20-session maturity (SPY calendar)
SELECT reentry_shape,
  COUNT(*) FILTER (WHERE (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker='SPY' AND d.trade_date > t.fire_date) >= 20) AS mature,
  COUNT(*) FILTER (WHERE (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker='SPY' AND d.trade_date > t.fire_date) < 20) AS immature
FROM mi_delayed_entry_trigger t WHERE rung='ep_low_reclaim' AND fire_date >= DATE '2026-09-02' AND realized_r_trail_075 IS NOT NULL
GROUP BY 1 ORDER BY 1;
\echo == R4. last settle run stamps (did the 10-13 EOD settle run?)
SELECT MAX(settled_at AT TIME ZONE 'America/New_York') AS last_inc_settle_et,
       MAX(settled_at_075 AT TIME ZONE 'America/New_York') AS last_075_settle_et,
       MAX(created_at AT TIME ZONE 'America/New_York') AS last_create_et
FROM mi_delayed_entry_trigger;
