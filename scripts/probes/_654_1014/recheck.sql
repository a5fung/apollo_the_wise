-- #654 re-check 2026-10-14 (read-only): failed-breakout telemetry stamped yet? recent TRIGGERED?
SELECT count(*) AS rows, count(failed_at) AS failed_at_stamped, count(low_after_breakout) AS low_after_breakout_stamped
  FROM mi_flag_candidates;
SELECT scan_date, ticker, stage FROM mi_flag_candidates
 WHERE stage = 'TRIGGERED' AND scan_date >= DATE '2026-10-01' ORDER BY scan_date DESC, ticker LIMIT 20;
