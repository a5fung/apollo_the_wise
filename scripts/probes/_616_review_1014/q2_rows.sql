\set QUIET 1
\pset format csv
\pset tuples_only off
WITH cal AS (SELECT trade_date FROM mi_daily_closes WHERE ticker='SPY' AND trade_date >= DATE '2026-08-20'),
lastd AS (SELECT MAX(trade_date) AS d FROM cal)
SELECT t.id, t.rung, t.ticker, t.ep_date, t.fire_date, t.fire_minute_et, t.resolution,
       (SELECT COUNT(*) FROM cal c, lastd WHERE c.trade_date > t.fire_date AND c.trade_date <= lastd.d) AS sess_after_fire,
       (SELECT d FROM lastd) AS last_bar,
       EXISTS (SELECT 1 FROM mi_ep_alerts a WHERE a.ticker=t.ticker AND a.alert_date=t.ep_date AND COALESCE(a.source,'live')='live') AS live_ep,
       t.entry_price, t.stop_price, t.stop_width_pct, t.ep_adr20_n, t.pattern_version, t.settle_version,
       t.outcome, t.realized_r, t.outcome_trail, t.realized_r_trail, t.reached_4r, t.mfe_r, t.stop_hit_date,
       t.stop_width_pct_075, t.outcome_075, t.realized_r_075, t.outcome_trail_075, t.realized_r_trail_075, t.reached_4r_075, t.mfe_r_075, t.settle_version_075, t.settled_at_075,
       t.stop_width_pct_100, t.outcome_100, t.realized_r_100, t.outcome_trail_100, t.realized_r_trail_100, t.reached_4r_100, t.mfe_r_100, t.settle_version_100, t.settled_at_100
FROM mi_delayed_entry_trigger t
WHERE t.reentry_shape='first' AND t.fire_date >= DATE '2026-08-28'
ORDER BY t.rung, t.fire_date, t.id;
