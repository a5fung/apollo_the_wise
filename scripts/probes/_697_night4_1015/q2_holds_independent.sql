-- READ-ONLY. Independent hold re-derivation (LATERAL prior-row join, NOT the LAG window of verify_hold_live.sql), 10-12..10-15.
-- prior = ticker's most recent row with scan_date in [d-5, d). raw = COALESCE(held_from_stage, stage).
-- NEW rule: hold iff raw in WATCH+ AND prior not a hold AND rank(raw) < rank(prior.stage). OLD rule: without "prior not a hold".
SET default_transaction_read_only = on;
SET statement_timeout = '60s';
\echo '== H1. per night: rows, actual holds, NEW-rule expected holds, mismatches vs NEW rule, OLD-rule holds, rows where OLD != NEW'
WITH r AS (
  SELECT c.scan_date, c.ticker, c.stage, c.held_from_stage, COALESCE(c.held_from_stage, c.stage) AS raw,
         p.scan_date AS p_date, p.stage AS p_stage, p.held_from_stage AS p_held
  FROM mi_flag_candidates c
  LEFT JOIN LATERAL (SELECT x.scan_date, x.stage, x.held_from_stage FROM mi_flag_candidates x
                     WHERE x.ticker = c.ticker AND x.scan_date < c.scan_date AND x.scan_date >= c.scan_date - 5
                     ORDER BY x.scan_date DESC LIMIT 1) p ON true
  WHERE c.scan_date BETWEEN DATE '2026-10-12' AND DATE '2026-10-15'
), k AS (
  SELECT r.*,
    array_position(ARRAY['unqualified','WATCH','TIGHTENING','COILED','TRIGGERED'], raw)     AS raw_rk,
    array_position(ARRAY['unqualified','WATCH','TIGHTENING','COILED','TRIGGERED'], p_stage) AS p_rk
  FROM r
), v AS (
  SELECT k.*,
    (raw IN ('WATCH','TIGHTENING','COILED','TRIGGERED') AND p_held IS NULL AND p_rk IS NOT NULL AND raw_rk < p_rk) AS new_holds,
    (raw IN ('WATCH','TIGHTENING','COILED','TRIGGERED')                     AND p_rk IS NOT NULL AND raw_rk < p_rk) AS old_holds
  FROM k
)
SELECT scan_date, count(*) rows,
  count(*) FILTER (WHERE held_from_stage IS NOT NULL) actual_holds,
  count(*) FILTER (WHERE new_holds) new_rule_holds,
  count(*) FILTER (WHERE (new_holds AND NOT (held_from_stage IS NOT NULL AND stage = p_stage))
                      OR (NOT new_holds AND held_from_stage IS NOT NULL)) mismatches_vs_new,
  count(*) FILTER (WHERE old_holds) old_rule_holds,
  count(*) FILTER (WHERE old_holds <> new_holds) old_ne_new
FROM v GROUP BY 1 ORDER BY 1;
\echo '== H2. 10-15 rows whose prior row was WATCH-or-better OR a hold (the hold-eligible population)'
WITH r AS (
  SELECT c.scan_date, c.ticker, c.stage, c.held_from_stage, COALESCE(c.held_from_stage, c.stage) AS raw,
         p.scan_date AS p_date, p.stage AS p_stage, p.held_from_stage AS p_held
  FROM mi_flag_candidates c
  LEFT JOIN LATERAL (SELECT x.scan_date, x.stage, x.held_from_stage FROM mi_flag_candidates x
                     WHERE x.ticker = c.ticker AND x.scan_date < c.scan_date AND x.scan_date >= c.scan_date - 5
                     ORDER BY x.scan_date DESC LIMIT 1) p ON true
  WHERE c.scan_date = DATE '2026-10-15'
), k AS (
  SELECT r.*,
    array_position(ARRAY['unqualified','WATCH','TIGHTENING','COILED','TRIGGERED'], raw)     AS raw_rk,
    array_position(ARRAY['unqualified','WATCH','TIGHTENING','COILED','TRIGGERED'], p_stage) AS p_rk
  FROM r
)
SELECT ticker, p_date, p_stage, p_held, raw, stage, held_from_stage,
       (raw IN ('WATCH','TIGHTENING','COILED','TRIGGERED') AND p_held IS NULL AND p_rk IS NOT NULL AND raw_rk < p_rk) AS new_rule_holds,
       (raw IN ('WATCH','TIGHTENING','COILED','TRIGGERED') AND p_rk IS NOT NULL AND raw_rk < p_rk) AS old_rule_holds
FROM k WHERE p_stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED') OR p_held IS NOT NULL ORDER BY 1;
\echo '== H3. tickers whose latest row in [10-10, 10-15) is a hold = what the 10-15 scan should log as holds_carried'
SELECT p.ticker, p.scan_date, p.stage, p.held_from_stage
FROM (SELECT DISTINCT ON (ticker) ticker, scan_date, stage, held_from_stage FROM mi_flag_candidates
      WHERE scan_date < DATE '2026-10-15' AND scan_date >= DATE '2026-10-15' - 5 ORDER BY ticker, scan_date DESC) p
WHERE p.held_from_stage IS NOT NULL;
\echo '== H4. every hold row ever written on/after 10-09'
SELECT ticker, scan_date, stage, held_from_stage FROM mi_flag_candidates WHERE held_from_stage IS NOT NULL AND scan_date >= DATE '2026-10-09' ORDER BY scan_date, ticker;
