-- READ-ONLY. VERIFIER. Independent hold re-derivation (LATERAL prior-row join, not the LAG window of verify_hold_live.sql).
-- prior = the ticker's most recent row with scan_date in [d-5, d)  (db.get_yesterday_flag_state).
-- raw   = COALESCE(held_from_stage, stage). Only WATCH..TRIGGERED raw reads reach stage_after_hold (gate failures return early).
-- NEW rule: hold iff raw in WATCH+ AND prior not a hold AND rank(raw) < rank(prior.stage)  (_STAGE_ORDER: unqualified..TRIGGERED; INVALIDATED unranked)
-- OLD rule: same without the "prior not a hold" clause.
SET default_transaction_read_only = on;
SET statement_timeout = '60s';
\echo '== V2a. per night: rows, actual holds, NEW-rule expected holds, mismatches vs NEW rule, OLD-rule holds, rows where OLD != NEW'
WITH r AS (
  SELECT c.scan_date, c.ticker, c.stage, c.held_from_stage, COALESCE(c.held_from_stage, c.stage) AS raw,
         p.scan_date AS p_date, p.stage AS p_stage, p.held_from_stage AS p_held
  FROM mi_flag_candidates c
  LEFT JOIN LATERAL (SELECT x.scan_date, x.stage, x.held_from_stage FROM mi_flag_candidates x
                     WHERE x.ticker = c.ticker AND x.scan_date < c.scan_date AND x.scan_date >= c.scan_date - 5
                     ORDER BY x.scan_date DESC LIMIT 1) p ON true
  WHERE c.scan_date BETWEEN DATE '2026-10-12' AND DATE '2026-10-14'
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
\echo '== V2b. every row where a hold is expected under EITHER rule, or happened'
WITH r AS (
  SELECT c.scan_date, c.ticker, c.stage, c.held_from_stage, COALESCE(c.held_from_stage, c.stage) AS raw,
         p.scan_date AS p_date, p.stage AS p_stage, p.held_from_stage AS p_held
  FROM mi_flag_candidates c
  LEFT JOIN LATERAL (SELECT x.scan_date, x.stage, x.held_from_stage FROM mi_flag_candidates x
                     WHERE x.ticker = c.ticker AND x.scan_date < c.scan_date AND x.scan_date >= c.scan_date - 5
                     ORDER BY x.scan_date DESC LIMIT 1) p ON true
  WHERE c.scan_date BETWEEN DATE '2026-10-12' AND DATE '2026-10-14'
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
SELECT scan_date, ticker, p_date, p_stage, p_held, raw, stage, held_from_stage, new_holds, old_holds FROM v
WHERE new_holds OR old_holds OR held_from_stage IS NOT NULL ORDER BY 1,2;
\echo '== V2c. 10-14 rows whose prior row was WATCH-or-better (the hold-eligible population), all stages'
WITH r AS (
  SELECT c.scan_date, c.ticker, c.stage, c.held_from_stage, COALESCE(c.held_from_stage, c.stage) AS raw,
         p.scan_date AS p_date, p.stage AS p_stage, p.held_from_stage AS p_held
  FROM mi_flag_candidates c
  LEFT JOIN LATERAL (SELECT x.scan_date, x.stage, x.held_from_stage FROM mi_flag_candidates x
                     WHERE x.ticker = c.ticker AND x.scan_date < c.scan_date AND x.scan_date >= c.scan_date - 5
                     ORDER BY x.scan_date DESC LIMIT 1) p ON true
  WHERE c.scan_date BETWEEN DATE '2026-10-12' AND DATE '2026-10-14'
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
SELECT ticker, p_date, p_stage, p_held, raw, stage, held_from_stage FROM v
WHERE scan_date = DATE '2026-10-14' AND p_stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED') ORDER BY 1;
\echo '== V2d. GRAL rows 10-12..10-14, full row as json'
SELECT scan_date, row_to_json(c)::text FROM mi_flag_candidates c WHERE ticker='GRAL' AND scan_date >= DATE '2026-10-12' ORDER BY scan_date;
\echo '== V2e. flag_stage_flip_held audit rows per ET day since 10-09 vs holds written that scan_date'
SELECT (a.created_at AT TIME ZONE 'America/New_York')::date AS et_day, count(*) audit_rows, string_agg(a.id::text||' '||a.summary, '; ' ORDER BY a.id) rows,
       (SELECT count(*) FROM mi_flag_candidates c WHERE c.scan_date = (a.created_at AT TIME ZONE 'America/New_York')::date AND c.held_from_stage IS NOT NULL) holds_that_date
FROM mi_audit_log a WHERE a.event_type='flag_stage_flip_held' AND a.created_at >= TIMESTAMPTZ '2026-10-09 00:00-04'
GROUP BY 1 ORDER BY 1;
\echo '== V2f. pre-registered for 10-15: tickers whose latest row in [10-10, 10-15) is a hold (= holds_carried the 10-15 scan should log)'
SELECT ticker, scan_date, stage, held_from_stage FROM (
  SELECT DISTINCT ON (ticker) ticker, scan_date, stage, held_from_stage FROM mi_flag_candidates
  WHERE scan_date < DATE '2026-10-15' AND scan_date >= DATE '2026-10-15' - 5 ORDER BY ticker, scan_date DESC) z
WHERE held_from_stage IS NOT NULL;
