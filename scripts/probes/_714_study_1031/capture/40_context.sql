SET default_transaction_read_only = on;
-- #714 capture, file 40_context.sql. READ-ONLY, $0. Registered in docs/analysis/ep_float_neglect_prereg_2026-10-31.md
-- (frozen BEFORE any output of these files was read). Output = psql -A -F "|": each \echo '=== NAME' line
-- starts a section, the next line is its header row, then data rows, then a "(N rows)" footer.
-- Every ET conversion goes through AT TIME ZONE 'America/New_York'. Nothing here writes, locks or creates.
-- CONTEXT. Regime per date, RS at D-1, RS history for the labelled boards, analyst-coverage as-of rows, market-cap
-- snapshots (CURRENT, not point-in-time: flagged by snapshot date), security type, sector, splits.

\echo '=== REGIME'
-- day-level; the stored acting bar and regime label per session
SELECT regime_date, regime, ep_threshold, spy_vs_50ma, spy_vs_200ma, qqq_vs_50ma, vix, breadth_pct_above_40ma, t2108
FROM mi_market_regime WHERE regime_date BETWEEN DATE '2026-04-01' AND (now() AT TIME ZONE 'America/New_York')::date ORDER BY regime_date;
\echo '=== RS_PREV'
-- mi_stock_scores row of the last session strictly BEFORE the scan date; NULL = not in the ~2,400-name pool
WITH lab(ticker, scan_date) AS (VALUES
  ('BFLY', DATE '2026-06-18'),
  ('PLTR', DATE '2026-08-04'),
  ('ABNB', DATE '2026-08-07'),
  ('TEAM', DATE '2026-08-07'),
  ('HTFL', DATE '2026-08-14'),
  ('MRNA', DATE '2026-08-19'),
  ('CHPT', DATE '2026-09-03'),
  ('PENG', DATE '2026-10-07')),
raw AS (
  SELECT l.* FROM mi_ep_scan_log l
  WHERE l.scan_date BETWEEN DATE '2026-05-01' AND DATE '2026-10-09' AND l.ep_score IS NOT NULL),
scored AS (
  SELECT DISTINCT ON (r.ticker, r.scan_date) r.*
  FROM raw r
  ORDER BY r.ticker, r.scan_date,
           (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC,
           r.ep_score DESC NULLS LAST, r.scan_time_et DESC NULLS LAST),
labrows AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l JOIN lab ON lab.ticker = l.ticker AND lab.scan_date = l.scan_date
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
pop AS (
  SELECT * FROM scored
  UNION ALL
  SELECT * FROM labrows lr
  WHERE NOT EXISTS (SELECT 1 FROM scored s WHERE s.ticker = lr.ticker AND s.scan_date = lr.scan_date)),
board_all AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l
  WHERE l.scan_date IN (SELECT DISTINCT scan_date FROM lab)
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
keys AS (
  SELECT ticker, scan_date FROM pop
  UNION
  SELECT ticker, scan_date FROM board_all),
key_tk AS (SELECT DISTINCT ticker FROM keys)
SELECT k.ticker, k.scan_date, s.score_date, s.rs_rank, s.rs_composite, s.rs_1m, s.rs_3m, s.rs_6m, s.adv_20, s.close AS score_close,
  (SELECT count(*) FROM mi_stock_scores s2 WHERE s2.score_date = s.score_date) AS pool_size_that_day
FROM keys k
LEFT JOIN LATERAL (
  SELECT x.* FROM mi_stock_scores x WHERE x.ticker = k.ticker AND x.score_date < k.scan_date ORDER BY x.score_date DESC LIMIT 1) s ON TRUE
ORDER BY k.scan_date, k.ticker;
\echo '=== RS_HIST_LABELLED'
-- RS of every labelled EP and every SCORED rival on the 7 labelled dates, 400 calendar days before each date; the out-of-favour read is Population A only
WITH lab(ticker, scan_date) AS (VALUES
  ('BFLY', DATE '2026-06-18'),
  ('PLTR', DATE '2026-08-04'),
  ('ABNB', DATE '2026-08-07'),
  ('TEAM', DATE '2026-08-07'),
  ('HTFL', DATE '2026-08-14'),
  ('MRNA', DATE '2026-08-19'),
  ('CHPT', DATE '2026-09-03'),
  ('PENG', DATE '2026-10-07')),
raw AS (
  SELECT l.* FROM mi_ep_scan_log l
  WHERE l.scan_date BETWEEN DATE '2026-05-01' AND DATE '2026-10-09' AND l.ep_score IS NOT NULL),
scored AS (
  SELECT DISTINCT ON (r.ticker, r.scan_date) r.*
  FROM raw r
  ORDER BY r.ticker, r.scan_date,
           (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC,
           r.ep_score DESC NULLS LAST, r.scan_time_et DESC NULLS LAST),
labrows AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l JOIN lab ON lab.ticker = l.ticker AND lab.scan_date = l.scan_date
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
pop AS (
  SELECT * FROM scored
  UNION ALL
  SELECT * FROM labrows lr
  WHERE NOT EXISTS (SELECT 1 FROM scored s WHERE s.ticker = lr.ticker AND s.scan_date = lr.scan_date)),
board_all AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l
  WHERE l.scan_date IN (SELECT DISTINCT scan_date FROM lab)
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
keys AS (
  SELECT ticker, scan_date FROM pop
  UNION
  SELECT ticker, scan_date FROM board_all),
key_tk AS (SELECT DISTINCT ticker FROM keys)
SELECT b.ticker, b.scan_date, s.score_date, s.rs_rank, s.rs_composite, s.rs_1m, s.rs_3m, s.rs_6m
FROM board_all b
JOIN mi_stock_scores s ON s.ticker = b.ticker AND s.score_date < b.scan_date AND s.score_date >= b.scan_date - 400
WHERE b.ep_score IS NOT NULL OR EXISTS (SELECT 1 FROM lab WHERE lab.ticker = b.ticker AND lab.scan_date = b.scan_date)
ORDER BY b.scan_date, b.ticker, s.score_date;
\echo '=== ANALYST_ASOF'
-- latest stored estimate row read strictly BEFORE the scan date, one per period_type; table starts 2026-08-31, so most pre-September keys are NULL by construction
WITH lab(ticker, scan_date) AS (VALUES
  ('BFLY', DATE '2026-06-18'),
  ('PLTR', DATE '2026-08-04'),
  ('ABNB', DATE '2026-08-07'),
  ('TEAM', DATE '2026-08-07'),
  ('HTFL', DATE '2026-08-14'),
  ('MRNA', DATE '2026-08-19'),
  ('CHPT', DATE '2026-09-03'),
  ('PENG', DATE '2026-10-07')),
raw AS (
  SELECT l.* FROM mi_ep_scan_log l
  WHERE l.scan_date BETWEEN DATE '2026-05-01' AND DATE '2026-10-09' AND l.ep_score IS NOT NULL),
scored AS (
  SELECT DISTINCT ON (r.ticker, r.scan_date) r.*
  FROM raw r
  ORDER BY r.ticker, r.scan_date,
           (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC,
           r.ep_score DESC NULLS LAST, r.scan_time_et DESC NULLS LAST),
labrows AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l JOIN lab ON lab.ticker = l.ticker AND lab.scan_date = l.scan_date
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
pop AS (
  SELECT * FROM scored
  UNION ALL
  SELECT * FROM labrows lr
  WHERE NOT EXISTS (SELECT 1 FROM scored s WHERE s.ticker = lr.ticker AND s.scan_date = lr.scan_date)),
board_all AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l
  WHERE l.scan_date IN (SELECT DISTINCT scan_date FROM lab)
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
keys AS (
  SELECT ticker, scan_date FROM pop
  UNION
  SELECT ticker, scan_date FROM board_all),
key_tk AS (SELECT DISTINCT ticker FROM keys)
SELECT k.ticker, k.scan_date, pt.period_type,
  ae.as_of_date, ae.valid_from_date, ae.period_end_date, ae.num_analysts_eps, ae.num_analysts_revenue, ae.source
FROM keys k
CROSS JOIN (VALUES ('quarter'), ('annual')) AS pt(period_type)
LEFT JOIN LATERAL (
  SELECT x.* FROM mi_analyst_estimates x
  WHERE x.ticker = k.ticker AND x.period_type = pt.period_type AND x.as_of_date < k.scan_date
  ORDER BY x.as_of_date DESC, x.period_end_date ASC LIMIT 1) ae ON TRUE
ORDER BY k.scan_date, k.ticker, pt.period_type;
\echo '=== SPLITS'
-- every stored split of every ticker in Population A/B/R2 since 2021; stage 2 flags windows that contain one
WITH lab(ticker, scan_date) AS (VALUES
  ('BFLY', DATE '2026-06-18'),
  ('PLTR', DATE '2026-08-04'),
  ('ABNB', DATE '2026-08-07'),
  ('TEAM', DATE '2026-08-07'),
  ('HTFL', DATE '2026-08-14'),
  ('MRNA', DATE '2026-08-19'),
  ('CHPT', DATE '2026-09-03'),
  ('PENG', DATE '2026-10-07')),
raw AS (
  SELECT l.* FROM mi_ep_scan_log l
  WHERE l.scan_date BETWEEN DATE '2026-05-01' AND DATE '2026-10-09' AND l.ep_score IS NOT NULL),
scored AS (
  SELECT DISTINCT ON (r.ticker, r.scan_date) r.*
  FROM raw r
  ORDER BY r.ticker, r.scan_date,
           (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC,
           r.ep_score DESC NULLS LAST, r.scan_time_et DESC NULLS LAST),
labrows AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l JOIN lab ON lab.ticker = l.ticker AND lab.scan_date = l.scan_date
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
pop AS (
  SELECT * FROM scored
  UNION ALL
  SELECT * FROM labrows lr
  WHERE NOT EXISTS (SELECT 1 FROM scored s WHERE s.ticker = lr.ticker AND s.scan_date = lr.scan_date)),
board_all AS (
  SELECT DISTINCT ON (l.ticker, l.scan_date) l.*
  FROM mi_ep_scan_log l
  WHERE l.scan_date IN (SELECT DISTINCT scan_date FROM lab)
  ORDER BY l.ticker, l.scan_date,
           (l.ep_score IS NOT NULL) DESC,
           (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) DESC,
           l.ep_score DESC NULLS LAST, l.scan_time_et DESC NULLS LAST),
keys AS (
  SELECT ticker, scan_date FROM pop
  UNION
  SELECT ticker, scan_date FROM board_all),
key_tk AS (SELECT DISTINCT ticker FROM keys)
SELECT sp.ticker, sp.execution_date, sp.split_from, sp.split_to, sp.adjustment_applied, sp.adjustment_outcome, sp.applied_factor
FROM mi_splits sp
WHERE sp.ticker IN (SELECT ticker FROM key_tk) AND sp.execution_date >= DATE '2021-01-01'
ORDER BY sp.ticker, sp.execution_date;
