\set QUIET 1
\pset format csv
SELECT t.id, t.rung, t.reentry_shape, t.ticker, t.ep_date, t.fire_date, t.fire_minute_et,
       (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker='SPY' AND d.trade_date > t.fire_date) AS spy_after,
       (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker=t.ticker AND d.trade_date > t.fire_date) AS own_after,
       t.entry_price, t.stop_price, t.stop_price_075, t.stop_price_100, t.stop_width_pct, t.stop_width_pct_075, t.stop_width_pct_100,
       t.ep_adr20_dollar, t.day_low, t.day0_post_low, t.day0_post_high, t.day0_resolved,
       t.outcome, t.realized_r, t.outcome_trail, t.realized_r_trail, t.reached_4r, t.mfe_r,
       t.outcome_075, t.realized_r_075, t.outcome_trail_075, t.realized_r_trail_075, t.reached_4r_075, t.mfe_r_075,
       t.outcome_100, t.realized_r_100, t.outcome_trail_100, t.realized_r_trail_100, t.reached_4r_100, t.mfe_r_100,
       (t.settled_at_075 AT TIME ZONE 'America/New_York')::date AS settled_075_et,
       (t.settled_at_100 AT TIME ZONE 'America/New_York')::date AS settled_100_et
FROM mi_delayed_entry_trigger t
WHERE t.fire_date >= DATE '2026-09-02'
ORDER BY t.rung, t.reentry_shape, t.fire_date, t.id;
