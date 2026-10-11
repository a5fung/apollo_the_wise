SELECT safeguard, account_mode, state, last_transition_at
FROM mi_safeguard_state
WHERE safeguard IN ('profit_take_resting_limit', 'profit_take_oco', 'breakeven_at_broker')
ORDER BY safeguard, account_mode;
