SET default_transaction_read_only = on;
-- #714 capture, file 30_daily_bars.sql. READ-ONLY, $0. Registered in docs/analysis/ep_float_neglect_prereg_2026-10-31.md
-- (frozen BEFORE any output of these files was read). Output = psql -A -F "|": each \echo '=== NAME' line
-- starts a section, the next line is its header row, then data rows, then a "(N rows)" footer.
-- Every ET conversion goes through AT TIME ZONE 'America/New_York'. Nothing here writes, locks or creates.
-- DAILY BARS. mi_daily_closes is split-adjusted by the nightly ingest (see mi_splits in 40_context.sql).
-- BARS_POP: every Population-B/A ticker + SPY/QQQ/IWM from 2021-01-01 to the latest loaded session (the forward windows).
-- BARS_SECONDARY: tickers that were only LOGGED rivals on a labelled date (secondary rival set R2), from 2024-01-01
-- (the longest registered feature window is 504 sessions + 60 warm-up, so 2024-01-01 covers every 2026 board).
-- Pipe to gzip on the way out:  ... | gzip > out/30_daily_bars.out.gz

\echo '=== BARS_POP'
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
pop_tk AS (SELECT DISTINCT ticker FROM pop),
sec_tk AS (
  SELECT DISTINCT b.ticker FROM board_all b
  WHERE b.prev_close >= 4
    AND (COALESCE(b.quality_adv_dollar, b.adv * b.prev_close) IS NULL OR COALESCE(b.quality_adv_dollar, b.adv * b.prev_close) >= 3000000)
    AND b.ticker NOT IN (SELECT ticker FROM pop_tk))
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM mi_daily_closes d
WHERE d.trade_date >= DATE '2021-01-01'
  AND (d.ticker IN (SELECT ticker FROM pop_tk) OR d.ticker IN ('SPY', 'QQQ', 'IWM'))
ORDER BY d.ticker, d.trade_date;
\echo '=== BARS_SECONDARY'
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
pop_tk AS (SELECT DISTINCT ticker FROM pop),
sec_tk AS (
  SELECT DISTINCT b.ticker FROM board_all b
  WHERE b.prev_close >= 4
    AND (COALESCE(b.quality_adv_dollar, b.adv * b.prev_close) IS NULL OR COALESCE(b.quality_adv_dollar, b.adv * b.prev_close) >= 3000000)
    AND b.ticker NOT IN (SELECT ticker FROM pop_tk))
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM mi_daily_closes d
WHERE d.trade_date >= DATE '2024-01-01' AND d.ticker IN (SELECT ticker FROM sec_tk)
ORDER BY d.ticker, d.trade_date;
