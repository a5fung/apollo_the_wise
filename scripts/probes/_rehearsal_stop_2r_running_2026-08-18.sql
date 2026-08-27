-- Rehearsal for stop_2r_running_comparison (2026-08-18).
-- Proves the "new-rule realized R vs old-rule counterfactual R" join is executable.
-- old-rule counterfactual: -1.00R if the trade EVER touched -1R (old ORB-low unit,
-- which is what stop_ref/risk_per_share/touched_minus_1r are always computed against
-- per exit_path_shadow.py: stop_ref = orb_low if orb_low is not None else hard_stop),
-- else = the trade's own realized_r (old rule would have ridden the same path).
-- Read-only. No writes. THE LINE: nothing here feeds any grading/entry/sizing path.
WITH exit_rows AS (
  SELECT trade_id, ticker, alert_date, fill_day, account_mode, signal_type,
         realized_r, exit_reason, exit_price
  FROM mi_exit_path_shadow WHERE is_exit_day = true
),
touch_hist AS (
  SELECT trade_id, BOOL_OR(touched_minus_1r) AS ever_touched_minus_1r
  FROM mi_exit_path_shadow
  GROUP BY trade_id
)
SELECT e.trade_id, e.ticker, e.alert_date, e.fill_day, e.account_mode, e.signal_type,
       e.realized_r, e.exit_reason,
       t.ever_touched_minus_1r,
       CASE WHEN t.ever_touched_minus_1r THEN -1.0 ELSE e.realized_r END AS old_rule_counterfactual_r,
       (e.fill_day >= DATE '2026-08-16') AS is_new_rule_trade
FROM exit_rows e
JOIN touch_hist t ON t.trade_id = e.trade_id
ORDER BY e.fill_day, e.ticker;
