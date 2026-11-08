SET default_transaction_read_only = on;
-- #720 §7 runner_rule_sweep_recut: any live/global toggle transition since the current exit era started voids the 08-29 runner read.
\copy (SELECT * FROM mi_safeguard_state WHERE account_mode IN ('live', 'global') ORDER BY last_transition_at DESC NULLS LAST) TO STDOUT WITH CSV HEADER
