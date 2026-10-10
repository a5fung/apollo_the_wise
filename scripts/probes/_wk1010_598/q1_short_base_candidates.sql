-- READ-ONLY. #598 render fix (wk1010): TIGHTENING / COILED rows of the last 30 days, with exactly
-- the fields the render surfaces read. Used to (a) confirm the 1.00 ratios at base_age <= 5 on
-- live data, (b) confirm fresh_2bar_tr_pct / atr14_pct are populated there, (c) pick a real
-- current candidate for the sample render.
SELECT scan_date, ticker, stage, base_age, runup_pct, pivot_high_price,
       range_contraction_ratio, vol_contraction_ratio,
       fresh_tight_fires, fresh_2bar_tr_pct, atr14_pct, held_from_stage, reason
FROM mi_flag_candidates
WHERE stage IN ('TIGHTENING', 'COILED')
  AND scan_date >= CURRENT_DATE - 30
ORDER BY scan_date DESC, stage, base_age, ticker;
