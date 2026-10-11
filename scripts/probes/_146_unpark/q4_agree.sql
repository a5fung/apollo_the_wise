-- #146 unpark: do the breakout tracking tables and mi_flag_candidates agree? For EVERY mi_htf_breakout_shadow row:
--   parent_stage (what the break recorded) vs the stage of the candidate row it points at (ticker, parent_scan_date),
--   and what the SAME evening's EOD scan read for that ticker on the break date (ticker, scan_date = break_date).
-- SELECT-only, captured once.
SELECT s.id, s.ticker, s.break_date, s.parent_scan_date, s.parent_stage,
       p.stage AS parent_row_stage, p.held_from_stage AS parent_row_held,
       e.stage AS eod_stage, e.held_from_stage AS eod_held, e.reason AS eod_reason,
       s.would_reject_reason, s.outcome, s.realized_r, s.settle_abstain_reason
FROM mi_htf_breakout_shadow s
LEFT JOIN mi_flag_candidates p ON p.ticker = s.ticker AND p.scan_date = s.parent_scan_date
LEFT JOIN mi_flag_candidates e ON e.ticker = s.ticker AND e.scan_date = s.break_date
ORDER BY s.break_date, s.ticker;
