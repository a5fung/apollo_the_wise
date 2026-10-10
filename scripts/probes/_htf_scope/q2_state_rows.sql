WITH days AS (SELECT DISTINCT scan_date FROM mi_flag_candidates ORDER BY scan_date DESC LIMIT 60)
SELECT ticker, scan_date, stage, held_from_stage, base_age, pivot_high_date, pivot_high_price, base_high, base_low,
  runup_pct, flag_depth_pct, range_contraction_ratio, vol_contraction_ratio, last_body_pct, prev_body_pct,
  fresh_tight_fires, breakout_close, breakout_volume_ratio, failed_at, low_after_breakout, undercut_after_breakout,
  array_to_string(universe_sources,'+') srcs, reason
FROM mi_flag_candidates
WHERE scan_date IN (SELECT scan_date FROM days) AND stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED','INVALIDATED')
ORDER BY ticker, scan_date;
