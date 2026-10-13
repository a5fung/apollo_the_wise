-- runner_rule_sweep_recut read 45 on 10-13: which rule toggle supplied the 40 (read-only)
SELECT safeguard, account_mode, state, last_transition_at AT TIME ZONE 'America/New_York' AS et
  FROM mi_safeguard_state
 WHERE account_mode IN ('live','global')
   AND safeguard NOT IN ('drawdown_breaker','kill_scale_band','manual_trading_halt')
   AND last_transition_at >= DATE '2026-09-06';
