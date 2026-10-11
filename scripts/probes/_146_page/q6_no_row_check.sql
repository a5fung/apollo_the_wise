-- #146 detection page — closes the validity check from the other side. q3 holds only WATCH+/INVALIDATED/held/mna rows,
-- so the 20 replay WATCH+ ticker-days (arm A, since 09-08) with no q3 row are EITHER days prod never scanned the ticker
-- OR days prod scanned it and scored plain `unqualified` (which would be a pivot divergence between the continuous replay
-- chain and prod's gapped one). Any row returned here is a disagreement to name on the page. SELECT-only, captured once.
SELECT ticker, scan_date, stage, held_from_stage, reason, pivot_high_date, pivot_high_price, base_age
FROM mi_flag_candidates
WHERE (ticker, scan_date) IN (
  ('ETON', DATE '2026-09-08'), ('SENS', DATE '2026-09-08'), ('HTFL', DATE '2026-09-14'),
  ('UROY', DATE '2026-09-16'), ('UROY', DATE '2026-09-17'), ('UROY', DATE '2026-09-18'),
  ('STIM', DATE '2026-09-22'), ('UROY', DATE '2026-09-22'), ('UROY', DATE '2026-09-23'),
  ('AGEN', DATE '2026-09-24'), ('SENS', DATE '2026-09-24'), ('CYPH', DATE '2026-09-25'),
  ('CYPH', DATE '2026-09-30'), ('SENS', DATE '2026-09-30'), ('SENS', DATE '2026-10-01'),
  ('SENS', DATE '2026-10-02'), ('APPN', DATE '2026-10-05'), ('SENS', DATE '2026-10-05'),
  ('SENS', DATE '2026-10-06'), ('OABI', DATE '2026-10-09')
)
ORDER BY ticker, scan_date;
