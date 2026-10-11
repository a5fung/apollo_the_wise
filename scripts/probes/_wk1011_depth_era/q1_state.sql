-- READ-ONLY (SELECT only). #687/#482 flip-day duty, 2026-10-11: the depth toggle rows, stamped
-- rows, MAGNA53's phase, and the recorder populations the before/after replay will cover.
SELECT 'toggle' AS k, safeguard, account_mode, state, last_transition_at::text, updated_at::text
  FROM mi_safeguard_state WHERE safeguard = 'magna53_depth_exit';
SELECT 'stamped_rows' AS k, exit_rule, account_mode, signal_type, COUNT(*)
  FROM mi_live_trades WHERE exit_rule IS NOT NULL GROUP BY 2,3,4;
SELECT 'strategy' AS k, strategy_id, phase, enabled, live_real_enabled, profit_trigger_r, breakeven_arm_r
  FROM mi_strategies WHERE strategy_id IN ('magna53','magna53_smallcap','magna53_lowcap');
SELECT 'cf_fills' AS k, account_mode, COUNT(DISTINCT trade_id) AS trades, COUNT(*) AS rows, MIN(alert_date)::text, MAX(alert_date)::text
  FROM mi_live_fill_counterfactuals GROUP BY 2;
SELECT 'cf_era' AS k, exit_era, COUNT(*) FROM mi_live_fill_counterfactuals GROUP BY 2;
SELECT 'lane_rows' AS k, 'sustain' AS lane, replay_exit_era, outcome, COUNT(*) FROM mi_sustain_reject_replays GROUP BY 3,4
UNION ALL SELECT 'lane_rows', 'gap_near_miss', replay_exit_era, outcome, COUNT(*) FROM mi_gap_near_miss_replays GROUP BY 3,4
UNION ALL SELECT 'lane_rows', 'lowcap', replay_exit_era, outcome, COUNT(*) FROM mi_lowcap_lane_replays GROUP BY 3,4
UNION ALL SELECT 'lane_rows', 'lowcap_paper', replay_exit_era, outcome, COUNT(*) FROM mi_lowcap_paper_lane_replays GROUP BY 3,4;
SELECT 'open_trades' AS k, id, ticker, signal_type, account_mode, alert_date::text, exit_rule, status, remaining_shares
  FROM mi_live_trades WHERE status = 'filled' AND remaining_shares > 0 ORDER BY id;
SELECT 'cf_population' AS k, t.id, t.ticker, t.account_mode, t.alert_date::text, t.filled_at::text, t.status, t.exit_rule,
       (SELECT COUNT(*) FROM mi_live_fill_counterfactuals c WHERE c.trade_id = t.id) AS arms
  FROM mi_live_trades t WHERE t.signal_type = 'magna53' AND t.filled_at IS NOT NULL
   AND (t.filled_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-16' ORDER BY t.filled_at;
