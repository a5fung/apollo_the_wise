-- #146 detection page (2026-10-11) — every stored WATCH-or-better row since the 06-27 HTF rebuild, ALL tickers.
-- Two uses: (1) population leak check — a ticker with a stored WATCH+ row that is absent from q1_candidates.out
-- is a name the pre-filter lost; (2) validity — the replay's RAW read (held_from_stage when the row is a hold,
-- else stage) must reproduce prod's on the ticker-days both have, era >= 2026-09-08 (the #592 anchor fix live).
-- SELECT-only, captured once.
SELECT ticker, scan_date, stage, held_from_stage, reason, pivot_high_date, pivot_high_price, base_age,
       base_high, base_low, breakout_close, breakout_volume_ratio, range_contraction_ratio, vol_contraction_ratio,
       universe_sources
FROM mi_flag_candidates
WHERE scan_date >= '2026-06-29'
  AND (stage IN ('WATCH', 'TIGHTENING', 'COILED', 'TRIGGERED', 'INVALIDATED') OR held_from_stage IS NOT NULL
       OR reason LIKE 'mna_filter:%')
ORDER BY ticker, scan_date;
