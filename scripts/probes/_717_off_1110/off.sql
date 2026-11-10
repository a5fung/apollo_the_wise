-- #717: his "off" (2026-11-10 ~07:20 PT): "the charts are all wrong ... these charts look nothing like what he trades". The ONE write.
BEGIN;
UPDATE mi_safeguard_state SET state = 'off', last_transition_at = NOW(), updated_at = NOW()
 WHERE safeguard = 'breakout_v1_paper' AND account_mode = 'global' AND state = 'on';
SELECT safeguard, account_mode, state, last_transition_at FROM mi_safeguard_state WHERE safeguard = 'breakout_v1_paper';
COMMIT;
