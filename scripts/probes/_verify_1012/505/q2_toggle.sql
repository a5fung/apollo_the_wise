\d mi_safeguard_state
SELECT * FROM mi_safeguard_state WHERE ctid IN (SELECT ctid FROM mi_safeguard_state) AND (to_jsonb(mi_safeguard_state)::text ILIKE '%parent%');
