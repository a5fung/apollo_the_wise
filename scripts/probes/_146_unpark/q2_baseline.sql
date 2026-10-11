-- #146 unpark: the EXPECT baseline - what each scan date stored BEFORE the change, over the last 60 scan dates.
-- raw_triggered = stage TRIGGERED and not a hold (the only rows that get a triggered_from stamp).
-- SELECT-only, captured once.
SELECT scan_date,
       count(*) FILTER (WHERE stage = 'TRIGGERED' AND held_from_stage IS NULL) AS raw_triggered,
       count(*) FILTER (WHERE stage = 'TRIGGERED' AND held_from_stage IS NOT NULL) AS held_triggered,
       count(*) FILTER (WHERE stage = 'COILED') AS coiled,
       count(*) FILTER (WHERE stage = 'TIGHTENING') AS tightening,
       count(*) FILTER (WHERE stage = 'WATCH') AS watch,
       count(*) AS rows_total
FROM mi_flag_candidates
WHERE scan_date >= '2026-07-17'
GROUP BY scan_date
ORDER BY scan_date;
