SELECT safeguard, account_mode, state, last_transition_at
FROM mi_safeguard_state
WHERE safeguard LIKE '%subtheme%' OR safeguard LIKE '%merge%' OR safeguard LIKE '%theme%';
