SELECT ticker, scan_date, stage, held_from_stage, base_age, pivot_high_date, pivot_high_price, base_high, base_low,
  runup_pct, flag_depth_pct, depth_on_low, depth_on_close, sma20_margin, ma_stack_margin,
  range_contraction_ratio, vol_contraction_ratio, last_body_pct, prev_body_pct, fresh_tight_fires,
  array_to_string(universe_sources,'+') srcs, reason
FROM mi_flag_candidates
WHERE ticker IN ('CDNA','HNGE','MRNA','NCI','ATAI','OUST','SHAZ','REPL','GH','HPE')
ORDER BY ticker, scan_date;
