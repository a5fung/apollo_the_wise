-- #697 item 1: what the Friday "Flag Bases" section WOULD have rendered each Friday since the gate blanked
-- it (2026-08-02), from the stored board. For each Friday F, `_fetch_flag` reads MAX(scan_date) in
-- [F-7, F]; this returns that scan date's COILED / TIGHTENING rows with every column the renderer reads.
-- READ-ONLY, captured once -> q4_friday_boards.out
WITH fridays AS (
  SELECT d::date AS f FROM generate_series('2026-08-07'::date, '2026-10-09'::date, '7 days') d
),
scan AS (
  SELECT f, (SELECT MAX(scan_date) FROM mi_flag_candidates c WHERE c.scan_date >= f - 7 AND c.scan_date <= f) AS sd
  FROM fridays
)
SELECT s.f::text AS friday, s.sd::text AS scan_date, c.ticker, c.stage, c.base_age::text, c.runup_pct::text,
       c.range_contraction_ratio::text, c.vol_contraction_ratio::text, c.fresh_tight_fires::text,
       c.fresh_2bar_tr_pct::text, c.atr14_pct::text
FROM scan s
LEFT JOIN mi_flag_candidates c ON c.scan_date = s.sd AND c.stage IN ('COILED', 'TIGHTENING')
ORDER BY s.f, CASE c.stage WHEN 'COILED' THEN 0 ELSE 1 END, c.range_contraction_ratio NULLS LAST;
