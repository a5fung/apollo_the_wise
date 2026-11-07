SET default_transaction_read_only = on;
SELECT * FROM mi_safeguard_state WHERE account_mode='global' AND row_to_json(mi_safeguard_state)::text ILIKE '%breakout_v1%';
