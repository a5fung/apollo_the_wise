-- #146 unpark (2026-10-11): every stored mi_flag_candidates row since 2026-08-14 (the pivot carry reaches back 40
-- calendar days before the first replayed scan date, 09-29). Threads the replay's state from PROD's own stored labels.
-- SELECT-only, captured once.
SELECT ticker, scan_date, stage, held_from_stage, reason, pivot_high_date, pivot_high_price, base_age, base_high,
       base_low, breakout_close, breakout_volume_ratio
FROM mi_flag_candidates
WHERE scan_date >= '2026-08-14'
ORDER BY scan_date, ticker;
