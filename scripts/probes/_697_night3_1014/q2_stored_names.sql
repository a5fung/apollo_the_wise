-- READ-ONLY. DoD clause "a WATCH name absent from a night's scan universe still gets a row": the stored WATCH-or-better names of
-- the last 5 scan sessions before 2026-10-14, each with its latest stored stage/date, its 10-14 row, and whether it was admitted ONLY by a carry.
SET default_transaction_read_only = on;
SET statement_timeout = '30s';
WITH sess AS (
  SELECT scan_date, ROW_NUMBER() OVER (ORDER BY scan_date DESC) AS lag
  FROM (SELECT DISTINCT scan_date FROM mi_flag_candidates WHERE scan_date < DATE '2026-10-14' AND scan_date >= DATE '2026-10-14' - 60) s
  WHERE EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = s.scan_date)
), st AS (
  SELECT DISTINCT ON (c.ticker) c.ticker, c.stage AS last_stored_stage, c.scan_date AS last_stored_date, sess.lag
  FROM mi_flag_candidates c JOIN sess ON sess.scan_date = c.scan_date
  WHERE sess.lag <= 5 AND c.stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED')
  ORDER BY c.ticker, c.scan_date DESC
)
SELECT st.ticker, st.last_stored_stage, st.last_stored_date, st.lag AS sessions_ago,
       t.stage AS stage_1014, t.held_from_stage, t.universe_sources,
       (t.universe_sources && ARRAY['rs_top200','rs_1m_80','momentum_25pct','magna53_failed_r3','ninem_universe_watch']::text[]) AS organic,
       (t.universe_sources && ARRAY['flag_stage_carryforward','flag_pivot_window_carryforward']::text[]) AS carried
FROM st LEFT JOIN mi_flag_candidates t ON t.ticker = st.ticker AND t.scan_date = DATE '2026-10-14'
ORDER BY st.ticker;
