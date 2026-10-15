-- READ-ONLY. GRAL rows 10-13..10-15 in full (the discriminating name: stored COILED + held_from_stage WATCH on 10-14).
SET default_transaction_read_only = on;
SET statement_timeout = '60s';
\echo '== G1. GRAL compact, 10-12..10-15'
SELECT scan_date, stage, held_from_stage, base_age, score, reason, fresh_tight_fires, universe_sources
FROM mi_flag_candidates WHERE ticker='GRAL' AND scan_date >= DATE '2026-10-12' ORDER BY scan_date;
\echo '== G2. GRAL 10-15 row as json'
SELECT row_to_json(c) FROM mi_flag_candidates c WHERE ticker='GRAL' AND scan_date = DATE '2026-10-15';
