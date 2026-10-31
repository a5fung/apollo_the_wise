SET default_transaction_read_only = on;
-- #714 capture, file 50_fetch_lists.sql. READ-ONLY, $0. Registered in docs/analysis/ep_float_neglect_prereg_2026-10-31.md
-- (frozen BEFORE any output of these files was read). Output = psql -A -F "|": each \echo '=== NAME' line
-- starts a section, the next line is its header row, then data rows, then a "(N rows)" footer.
-- Every ET conversion goes through AT TIME ZONE 'America/New_York'. Nothing here writes, locks or creates.
-- EXTERNAL-FETCH LISTS (stage 1b; the fetches themselves are NOT SQL and NOT prod).
--   float      : yfinance Ticker.info['floatShares'] (the field the live score reads: collector.get_fmp_profile).
--   upgrades   : collector.get_recent_upgrade_events(ticker) (yfinance upgrades_downgrades, dated events).
-- Tier A = Population A (8 EPs + their scored rivals): mandatory for the labelled-EP read.
-- Tier B = rest of Population B with no stored float: optional, extends the tail leg back before the float era.

\echo '=== FETCH_A'
-- Population A: one row per labelled EP and per scored rival; needs_fetch = no float on ANY stored tick
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
ticks AS (
  SELECT t.ticker, t.scan_date,
         count(*) AS n_ticks,
         count(*) FILTER (WHERE t.ep_score IS NOT NULL) AS n_scored_ticks,
         bool_or(t.filter_reason IS NULL AND t.score_tier IS NOT NULL) AS any_pass_tick,
         max(t.ep_score) AS max_score,
         max(t.float_shares) AS float_any_tick,
         count(t.float_shares) AS n_float_ticks,
         min(t.scan_time_et) AS first_tick_time,
         max(t.scan_time_et) AS last_tick_time,
         min(t.scan_time_et) FILTER (WHERE t.filter_reason IS NULL AND t.score_tier IS NOT NULL) AS first_pass_time,
         min(t.scan_time_et) FILTER (WHERE t.filter_reason IS NULL AND t.score_tier = 'HIGH') AS first_high_time
  FROM mi_ep_scan_log t
  WHERE (t.ticker, t.scan_date) IN (SELECT ticker, scan_date FROM board_all)
  GROUP BY t.ticker, t.scan_date)
SELECT b.ticker, b.scan_date,
  CASE WHEN lab.ticker IS NOT NULL THEN 'labelled_ep' WHEN b.ep_score IS NOT NULL THEN 'scored_rival' ELSE 'logged_rival' END AS role,
  b.float_shares AS float_stored_chosen_tick, t.float_any_tick,
  (COALESCE(b.float_shares, t.float_any_tick) IS NULL) AS needs_float_fetch
FROM board_all b
JOIN ticks t ON t.ticker = b.ticker AND t.scan_date = b.scan_date
LEFT JOIN lab ON lab.ticker = b.ticker AND lab.scan_date = b.scan_date
WHERE lab.ticker IS NOT NULL OR b.ep_score IS NOT NULL
ORDER BY b.scan_date, role, b.ticker;
\echo '=== FETCH_B'
-- Population B rows with NO stored float on any tick; distinct tickers = the fetch count
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
ticks AS (
  SELECT t.ticker, t.scan_date,
         count(*) AS n_ticks,
         count(*) FILTER (WHERE t.ep_score IS NOT NULL) AS n_scored_ticks,
         bool_or(t.filter_reason IS NULL AND t.score_tier IS NOT NULL) AS any_pass_tick,
         max(t.ep_score) AS max_score,
         max(t.float_shares) AS float_any_tick,
         count(t.float_shares) AS n_float_ticks,
         min(t.scan_time_et) AS first_tick_time,
         max(t.scan_time_et) AS last_tick_time,
         min(t.scan_time_et) FILTER (WHERE t.filter_reason IS NULL AND t.score_tier IS NOT NULL) AS first_pass_time,
         min(t.scan_time_et) FILTER (WHERE t.filter_reason IS NULL AND t.score_tier = 'HIGH') AS first_high_time
  FROM mi_ep_scan_log t
  WHERE (t.ticker, t.scan_date) IN (SELECT ticker, scan_date FROM pop)
  GROUP BY t.ticker, t.scan_date)
SELECT p.ticker, p.scan_date, (lab.ticker IS NOT NULL) AS is_labelled
FROM pop p
JOIN ticks t ON t.ticker = p.ticker AND t.scan_date = p.scan_date
LEFT JOIN lab ON lab.ticker = p.ticker AND lab.scan_date = p.scan_date
WHERE COALESCE(p.float_shares, t.float_any_tick) IS NULL
ORDER BY p.scan_date, p.ticker;
\echo '=== FETCH_COUNTS'
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
ticks AS (
  SELECT t.ticker, t.scan_date,
         count(*) AS n_ticks,
         count(*) FILTER (WHERE t.ep_score IS NOT NULL) AS n_scored_ticks,
         bool_or(t.filter_reason IS NULL AND t.score_tier IS NOT NULL) AS any_pass_tick,
         max(t.ep_score) AS max_score,
         max(t.float_shares) AS float_any_tick,
         count(t.float_shares) AS n_float_ticks,
         min(t.scan_time_et) AS first_tick_time,
         max(t.scan_time_et) AS last_tick_time,
         min(t.scan_time_et) FILTER (WHERE t.filter_reason IS NULL AND t.score_tier IS NOT NULL) AS first_pass_time,
         min(t.scan_time_et) FILTER (WHERE t.filter_reason IS NULL AND t.score_tier = 'HIGH') AS first_high_time
  FROM mi_ep_scan_log t
  WHERE (t.ticker, t.scan_date) IN (SELECT ticker, scan_date FROM board_all)
  GROUP BY t.ticker, t.scan_date),
fa AS (SELECT DISTINCT bb.ticker FROM board_all bb JOIN ticks t ON t.ticker = bb.ticker AND t.scan_date = bb.scan_date
       LEFT JOIN lab ON lab.ticker = bb.ticker AND lab.scan_date = bb.scan_date
       WHERE (lab.ticker IS NOT NULL OR bb.ep_score IS NOT NULL) AND COALESCE(bb.float_shares, t.float_any_tick) IS NULL),
fb AS (SELECT DISTINCT p.ticker FROM pop p JOIN ticks t ON t.ticker = p.ticker AND t.scan_date = p.scan_date
       WHERE COALESCE(p.float_shares, t.float_any_tick) IS NULL)
SELECT (SELECT count(*) FROM fa) AS tier_a_distinct_tickers_to_fetch,
       (SELECT count(*) FROM fb) AS tier_b_distinct_tickers_to_fetch,
       (SELECT count(*) FROM fb WHERE ticker NOT IN (SELECT ticker FROM fa)) AS tier_b_beyond_a;
