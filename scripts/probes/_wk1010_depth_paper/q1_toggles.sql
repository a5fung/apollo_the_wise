SELECT safeguard, account_mode, state, last_transition_at, updated_at
FROM mi_safeguard_state
WHERE safeguard IN ('magna53_depth_exit','profit_take_oco','profit_take_resting_limit','breakeven_at_broker','entry_ask_aware','lowcap_paper_lane')
ORDER BY safeguard, account_mode;
SELECT '---';
SELECT signal_type, account_mode, count(*) AS n, count(*) FILTER (WHERE exit_rule IS NOT NULL) AS stamped
FROM mi_live_trades GROUP BY 1,2 ORDER BY 1,2;
SELECT '---';
SELECT strategy_id, phase, enabled, live_real_enabled, max_concurrent_positions FROM mi_strategies WHERE strategy_id LIKE 'magna53%' ORDER BY 1;
SELECT '---';
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_safeguard_state' ORDER BY ordinal_position;
