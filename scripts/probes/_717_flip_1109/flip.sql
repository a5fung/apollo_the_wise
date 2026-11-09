-- #717 stage 3: his "Flip it" (2026-11-09 ~15:05 PT). Run AFTER tonight's deploy. The ONE write: the paper switch on.
BEGIN;
UPDATE mi_safeguard_state SET state = 'on', last_transition_at = NOW(), updated_at = NOW()
 WHERE safeguard = 'breakout_v1_paper' AND account_mode = 'global' AND state = 'off';
SELECT safeguard, account_mode, state, last_transition_at FROM mi_safeguard_state WHERE safeguard = 'breakout_v1_paper';
SELECT strategy_id, phase, enabled FROM mi_strategies WHERE strategy_id = 'breakout_v1';
COMMIT;
