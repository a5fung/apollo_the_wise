-- Corrected rehearsal for stop_2r_running_comparison (2026-08-18).
-- FIXES the bias in _rehearsal_stop_2r_running_2026-08-18.sql: that query scored
-- EVERY trade that ever touched -1R as a flat -1.00R old-rule counterfactual, even
-- when a partial had already been banked before the stop was touched -- overstating
-- the old rule's loss on any such trade (and flattering the new 2R rule by
-- comparison). Fix: credit the partial. A trade's OWN realized_r is the correct
-- old-rule counterfactual whenever a partial fired before the -1R touch, because
-- every one of these 20 closed trades pre-dates the 2026-08-16 stop change -- the
-- OLD rule WAS the live rule when they closed, so realized_r already IS what the
-- old rule produced. The flat -1.00R fallback is only used when the OLD stop was
-- touched AND no partial preceded it.
--
-- Ordering matters: breakeven_armed must be checked AS OF THE DAY THE -1R TOUCH
-- FIRST HAPPENED, not at exit -- a trade could in principle touch -1R on one day
-- and take a partial on a LATER day before finally exiting, in which case the
-- partial did NOT precede the old stop and flat -1.00 is still correct. touch_day
-- below picks out that first-touch row explicitly instead of trusting the exit
-- row's breakeven_armed value (which happens to coincide with the touch day only
-- because, on this population, every touch-and-partial trade touched -1R on its
-- exit day itself, so both formulations resolve to the same 20 numbers here --
-- pinning the more careful version for when a multi-day case shows up).
--
-- GUARD (advisor-caught, added before this shipped): `realized_r` is only a
-- valid old-rule counterfactual in the touched+partial branch when the OLD
-- rule was actually live for that trade (fill_day < 2026-08-16). On a NEW-rule
-- trade, touched_minus_1r/breakeven_armed still fire off the same ORB-low
-- anchor, but realized_r reflects what the WIDER (2R) stop produced past that
-- point, not what the old ORB-low stop would have done -- crediting it the
-- same way would silently collapse both arms of the comparison on exactly the
-- trades this review exists to discriminate. Those rows score NULL here (skip,
-- never fabricate a number) -- matches `scripts/stop_2r_counterfactual.
-- old_rule_counterfactual_r`'s guard exactly. None of the 20 rows below hit
-- this branch yet (all pre-cutover) -- AMLX (first new-rule fill, 2026-08-18)
-- will be the first candidate once it closes.
-- Read-only. No writes. THE LINE: nothing here feeds any grading/entry/sizing path.
WITH exit_rows AS (
  SELECT trade_id, ticker, alert_date, fill_day, account_mode, signal_type,
         realized_r, exit_reason, exit_price
  FROM mi_exit_path_shadow WHERE is_exit_day = true
),
touch_day AS (
  -- first trading_day per trade where touched_minus_1r = true, with that day's
  -- own breakeven_armed value (was a partial already booked by then?)
  SELECT DISTINCT ON (trade_id)
         trade_id, trading_day AS touch_trading_day, breakeven_armed AS armed_at_touch
  FROM mi_exit_path_shadow
  WHERE touched_minus_1r = true
  ORDER BY trade_id, trading_day ASC
)
SELECT e.trade_id, e.ticker, e.alert_date, e.fill_day, e.account_mode, e.signal_type,
       e.realized_r, e.exit_reason,
       (t.trade_id IS NOT NULL) AS ever_touched_minus_1r,
       COALESCE(t.armed_at_touch, false) AS partial_before_touch,
       (e.fill_day >= DATE '2026-08-16') AS is_new_rule_trade,
       CASE
         WHEN t.trade_id IS NULL THEN e.realized_r                          -- never touched -> old rule rides the same path
         WHEN NOT t.armed_at_touch THEN -1.0                                -- touched, no prior partial -> flat -1R stands
         WHEN e.fill_day < DATE '2026-08-16' THEN e.realized_r              -- touched + partial + OLD rule was live -> credit it
         ELSE NULL                                                          -- touched + partial + NEW rule was live -> refuse to score (guard)
       END AS old_rule_counterfactual_r_corrected,
       CASE WHEN t.trade_id IS NOT NULL THEN -1.0 ELSE e.realized_r END AS old_rule_counterfactual_r_naive
FROM exit_rows e
LEFT JOIN touch_day t ON t.trade_id = e.trade_id
ORDER BY e.fill_day, e.ticker;
