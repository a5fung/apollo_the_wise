-- verify #694 (b): recompute P (latest complete score_date <= scan_date-1, production SQL rule inlined)
-- and adv_20 x scan-row prev_close, rs_composite, rs_rank at P. Also any row at scan_date itself (must NOT be used). Read-only.
WITH pick(ticker, d) AS (VALUES
 ('SNOW',DATE '2026-05-07'),('PLTR',DATE '2026-08-04'),('UMC',DATE '2026-05-26'),('SBS',DATE '2026-10-05'),
 ('PAGS',DATE '2026-10-05'),('ROIV',DATE '2026-09-08'),('TIMB',DATE '2026-10-05'),('EAF',DATE '2026-09-08'),
 ('MRNA',DATE '2026-08-19'),('TEAM',DATE '2026-08-07'),('UMC',DATE '2026-05-06'),('HTFL',DATE '2026-08-14')),
pp AS (
 SELECT p.ticker, p.d,
  (SELECT counts.score_date FROM (
       SELECT score_date, COUNT(*) AS n FROM mi_stock_scores WHERE score_date <= p.d - 1 GROUP BY score_date) counts
    WHERE counts.n >= 0.5 * (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY n) FROM (
        SELECT COUNT(*) AS n FROM mi_stock_scores WHERE score_date <= p.d - 1 GROUP BY score_date ORDER BY score_date DESC LIMIT 10) recent)
    ORDER BY counts.score_date DESC LIMIT 1) AS p_date
 FROM pick p)
SELECT pp.ticker, pp.d, pp.p_date, s.adv_20, s.rs_composite, s.rs_rank,
       (SELECT l.prev_close FROM mi_ep_scan_log l WHERE l.ticker=pp.ticker AND l.scan_date=pp.d AND l.rank_by_gap IS NOT NULL
          AND (l.scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30' ORDER BY l.scan_time_et DESC LIMIT 1) prev_close_lasttick,
       (SELECT l.adv FROM mi_ep_scan_log l WHERE l.ticker=pp.ticker AND l.scan_date=pp.d AND l.rank_by_gap IS NOT NULL
          AND (l.scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30' ORDER BY l.scan_time_et DESC LIMIT 1) logged_adv,
       (SELECT l.adv_source FROM mi_ep_scan_log l WHERE l.ticker=pp.ticker AND l.scan_date=pp.d AND l.rank_by_gap IS NOT NULL
          AND (l.scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30' ORDER BY l.scan_time_et DESC LIMIT 1) logged_adv_source,
       s0.adv_20 adv20_on_scan_date, s0.rs_composite rs_comp_on_scan_date,
       (SELECT max(score_date) FROM mi_stock_scores x WHERE x.ticker=pp.ticker AND x.score_date < pp.d) latest_row_any_before
  FROM pp
  LEFT JOIN mi_stock_scores s ON s.ticker=pp.ticker AND s.score_date=pp.p_date
  LEFT JOIN mi_stock_scores s0 ON s0.ticker=pp.ticker AND s0.score_date=pp.d
 ORDER BY pp.d, pp.ticker;
