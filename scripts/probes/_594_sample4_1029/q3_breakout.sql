SET default_transaction_read_only = on;
\echo == gap-day bars
SELECT ticker, trade_date, open_price, high_price, low_price, close, volume FROM mi_daily_closes
WHERE (ticker, trade_date) IN (('AKAM','2026-09-25'),('PHVS','2026-09-08'),('DFTX','2026-09-14'),('GNRC','2026-09-17'),('ROIV','2026-09-08'),('CCL','2026-09-29'),('ODD','2026-09-09'),('SIG','2026-09-09'))
ORDER BY 1;
\echo == breakout shadow watch rows in the 10 sessions before each gap
SELECT w.ticker, w.scan_date, w.pole_date, round(w.pivot_k5::numeric,2) AS k5
FROM mi_consolidation_breakout_watch w
JOIN (VALUES ('AKAM','2026-09-25'::date),('PHVS','2026-09-08'),('DFTX','2026-09-14'),('GNRC','2026-09-17'),('ROIV','2026-09-08'),('CCL','2026-09-29'),('ODD','2026-09-09'),('SIG','2026-09-09')) s(t,d)
  ON w.ticker = s.t AND w.scan_date < s.d AND w.scan_date >= s.d - 14
ORDER BY 1,2;
\echo == breakout shadow entries on the gap day
SELECT e.ticker, e.entry_date, e.variant, e.status FROM mi_consolidation_breakout_entry e
JOIN (VALUES ('AKAM','2026-09-25'::date),('PHVS','2026-09-08'),('DFTX','2026-09-14'),('GNRC','2026-09-17'),('ROIV','2026-09-08'),('CCL','2026-09-29'),('ODD','2026-09-09'),('SIG','2026-09-09')) s(t,d)
  ON e.ticker = s.t AND e.entry_date = s.d ORDER BY 1,3;
