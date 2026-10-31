SET default_transaction_read_only = on;
\echo == live mode
SELECT * FROM mi_safeguard_state WHERE key ILIKE '%birth_gate%';
\echo == suppressions: first-crossing join to a DIFFERENT theme, since the dedup_only flip
SELECT id, name, first_seen, last_seen, sightings, status, mode, join_target, round(join_overlap::numeric,2) AS ov, array_length(tickers,1) AS n, tickers
FROM mi_theme_birth_candidates WHERE last_outcome = 'join' AND join_target IS NOT NULL AND join_target <> name AND sightings = 1
  AND first_seen >= '2026-09-14' ORDER BY first_seen, id;
\echo == mi_themes columns
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_themes' ORDER BY ordinal_position;
