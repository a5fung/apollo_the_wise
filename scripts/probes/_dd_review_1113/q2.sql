SET default_transaction_read_only = on;
SELECT safeguard, account_mode, state, last_transition_at FROM mi_safeguard_state WHERE safeguard ILIKE '%drawdown%';
SELECT count(*) FROM mi_live_trades WHERE account_mode='live' AND created_at > '2026-11-12 21:12+00';
