SET default_transaction_read_only = on;
-- #720 §6 absence rule: the breakout paper switch and the depth toggles, as of capture.
\copy (SELECT * FROM mi_safeguard_state WHERE safeguard IN ('breakout_v1_paper', 'magna53_depth_exit') ORDER BY safeguard, account_mode) TO STDOUT WITH CSV HEADER
