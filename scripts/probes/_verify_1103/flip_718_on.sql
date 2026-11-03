-- #718: his flip shadow -> on (his 'Ok.' 2026-11-03 to 'Switch it on? I recommend yes'; he authorized the write: 'i auth it'); SQL from docs/setups/magna53_ep.md 2026-10-31
INSERT INTO mi_safeguard_state (safeguard, account_mode, state, last_transition_at, updated_at) VALUES ('magna53_open_below_floor', 'global', 'on', NOW(), NOW()) ON CONFLICT (safeguard, account_mode) DO UPDATE SET state = EXCLUDED.state, last_transition_at = NOW(), updated_at = NOW();
SELECT safeguard, account_mode, state, last_transition_at FROM mi_safeguard_state WHERE safeguard = 'magna53_open_below_floor';
