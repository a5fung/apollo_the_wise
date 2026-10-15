SET default_transaction_read_only = on;
\set QUIET 1
\pset pager off
\pset format csv
SELECT t.id, t.rung, t.reentry_shape, t.ticker, t.ep_date, t.fire_date, t.fire_minute_et,
       (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker='SPY' AND d.trade_date > t.fire_date) AS spy_after,
       t.entry_price, t.stop_price, t.stop_price_025, t.stop_price_075, t.stop_price_100,
       t.stop_width_pct, t.stop_width_pct_025, t.stop_width_pct_075,
       t.ep_adr20_dollar, t.ep_adr20_n, t.day_high, t.day_low, t.day_close, t.day0_resolved, t.day0_post_low, t.day0_post_high,
       t.outcome, t.realized_r, t.outcome_trail, t.realized_r_trail,
       t.outcome_025, t.realized_r_025, t.outcome_trail_025, t.realized_r_trail_025, t.reached_4r_025,
       t.outcome_075, t.realized_r_075, t.outcome_trail_075, t.realized_r_trail_075,
       t.outcome_100, t.realized_r_trail_100
FROM mi_delayed_entry_trigger t
WHERE t.rung='ep_low_reclaim' AND t.reentry_shape='first'
ORDER BY t.fire_date, t.id;
