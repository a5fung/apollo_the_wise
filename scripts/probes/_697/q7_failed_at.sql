-- #697 item 2: has #654's failed_at ever stamped? (baseline for the EXPECT). READ-ONLY, captured once.
SELECT 'failed_at_rows' k, COUNT(*)::text a, COUNT(DISTINCT ticker)::text b, MIN(scan_date)::text c, MAX(scan_date)::text d
FROM mi_flag_candidates WHERE failed_at IS NOT NULL
UNION ALL
SELECT 'anchored_rows', COUNT(*)::text, COUNT(DISTINCT ticker)::text, MIN(scan_date)::text, MAX(scan_date)::text
FROM mi_flag_candidates WHERE low_after_breakout IS NOT NULL
UNION ALL
SELECT 'triggered_rows', COUNT(*)::text, COUNT(DISTINCT ticker)::text, MIN(scan_date)::text, MAX(scan_date)::text
FROM mi_flag_candidates WHERE stage = 'TRIGGERED' AND held_from_stage IS NULL;
