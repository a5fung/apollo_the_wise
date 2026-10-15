-- MRNA 2026-09-10..09-18: what our boards said around his 9/16 inside day and 9/17 breakout (read-only)
SELECT scan_date, stage, left(coalesce(reason,''),80) AS reason, triggered_from
  FROM mi_flag_candidates WHERE ticker='MRNA' AND scan_date BETWEEN DATE '2026-09-10' AND DATE '2026-09-18' ORDER BY scan_date;
SELECT fire_date, rung, reentry_shape, entry_price, stop_price, realized_r_trail, settled_at
  FROM mi_delayed_entry_trigger WHERE ticker='MRNA' ORDER BY fire_date;
SELECT d.trade_date, d.open, d.high, d.low, d.close, d.volume
  FROM mi_daily_closes d WHERE d.ticker='MRNA' AND d.trade_date BETWEEN DATE '2026-09-10' AND DATE '2026-09-18' ORDER BY 1;
