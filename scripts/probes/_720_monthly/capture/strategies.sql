SET default_transaction_read_only = on;
-- #720 §6 absence rule: the strategy rows (mi_strategies.enabled / phase are an on/off source beside the runtime switch; the env default is a third and is not in any table).
\copy (SELECT strategy_id, name, family, phase, enabled, live_real_enabled, signal_type, max_concurrent_positions, profit_trigger_r, breakeven_arm_r FROM mi_strategies ORDER BY strategy_id) TO STDOUT WITH CSV HEADER
