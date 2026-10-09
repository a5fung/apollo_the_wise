-- re-verify #694 (read-only). One pull, captured once.
\echo '### V12a per-day ranked pre-open board: last tick size AND the largest board at ANY pre-open tick (all days)'
WITH pre AS (
  SELECT scan_date, scan_time_et, ticker FROM mi_ep_scan_log
   WHERE scan_date BETWEEN '2026-04-13' AND '2026-10-08' AND rank_by_gap IS NOT NULL
     AND scan_time_et IS NOT NULL AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30'),
per_tick AS (SELECT scan_date, scan_time_et, count(*) n, count(DISTINCT ticker) nd FROM pre GROUP BY 1,2),
lt AS (SELECT scan_date, max(scan_time_et) t FROM per_tick GROUP BY 1)
SELECT p.scan_date,
       to_char(lt.t AT TIME ZONE 'America/New_York','HH24:MI:SS') last_tick,
       max(p.n) FILTER (WHERE p.scan_time_et = lt.t) n_last,
       max(p.nd) FILTER (WHERE p.scan_time_et = lt.t) nd_last,
       max(p.n) n_max_any_tick,
       count(*) FILTER (WHERE p.n > 20) n_ticks_over_20,
       count(*) n_ticks,
       (SELECT count(DISTINCT ticker) FROM pre x WHERE x.scan_date = p.scan_date) n_distinct_names_all_ticks
  FROM per_tick p JOIN lt USING (scan_date)
 GROUP BY p.scan_date, lt.t ORDER BY 1;
\echo '### V12b 10-05 and 09-17: board size per pre-open tick'
SELECT scan_date, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS.US') tick, count(*) n,
       count(*) FILTER (WHERE filter_reason LIKE 'outside top-%') n_cut_logged
  FROM mi_ep_scan_log
 WHERE scan_date IN ('2026-10-05','2026-09-17') AND rank_by_gap IS NOT NULL
   AND (scan_time_et AT TIME ZONE 'America/New_York')::time BETWEEN '09:00' AND '09:29:59'
 GROUP BY 1,2 ORDER BY 1,2;
\echo '### V12c every labelled pair: ranked pre-open ticks present, first/last such tick, rank at last day tick, any-row first time'
WITH lab(ticker, d, label) AS (VALUES
 ('UMC','2026-04-17','REAL_EP'),('QCOM','2026-04-24','REAL_EP'),('AMD','2026-04-24','REAL_EP'),('INTC','2026-04-24','REAL_EP'),
 ('UMC','2026-05-06','REAL_EP'),('ARM','2026-05-06','REAL_EP'),('SNOW','2026-05-07','REAL_EP'),('TDIC','2026-05-12','REAL_EP'),
 ('QURE','2026-05-29','REAL_EP'),('BFLY','2026-06-18','REAL_EP'),('PLTR','2026-08-04','REAL_EP'),('TEAM','2026-08-07','REAL_EP'),
 ('ABNB','2026-08-07','REAL_EP'),('HTFL','2026-08-14','REAL_EP'),('MRNA','2026-08-19','REAL_EP'),('CHPT','2026-09-03','REAL_EP'),
 ('PENG','2026-10-07','REAL_EP'),
 ('RNG','2026-07-24','GOOD'),('KRO','2026-08-06','GOOD'),('TBBB','2026-08-13','GOOD'),('CDNA','2026-07-16','GOOD'),('MAN','2026-07-16','GOOD'),
 ('BLZE','2026-08-04','GOOD'),('AVAH','2026-08-13','GOOD'),('HAE','2026-08-18','GOOD'),
 ('CAR','2026-04-21','BAD'),('CAR','2026-04-22','BAD'),('GDC','2026-05-06','BAD'),('MRAM','2026-05-13','BAD'),('CRWG','2026-06-01','BAD'),
 ('AVGU','2026-06-02','BAD'),('ABVX','2026-06-03','BAD'),('NVTS','2026-06-03','BAD'),('NVTX','2026-06-03','BAD'),('RUM','2026-06-04','BAD'),
 ('MRLN','2026-06-05','BAD'),('JLHL','2026-06-08','BAD'),('QH','2026-06-18','BAD'),('QTTB','2026-07-13','BAD'),('ADVB','2026-07-24','BAD'),
 ('HURN','2026-07-29','BAD'),('IPCX','2026-07-29','BAD'),('IBTA','2026-08-04','BAD'),('YOU','2026-08-05','BAD'),('AEVA','2026-08-06','BAD'),
 ('BW','2026-08-11','BAD'),('FRMI','2026-08-11','BAD'),('AEHR','2026-08-14','BAD'),('LPTH','2026-08-14','BAD'),('RARE','2026-08-20','BAD')),
lt AS (SELECT scan_date, max(scan_time_et) t FROM mi_ep_scan_log
        WHERE scan_date BETWEEN '2026-04-13' AND '2026-10-08' AND rank_by_gap IS NOT NULL
          AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30' GROUP BY 1)
SELECT l.ticker, l.d, l.label,
  (SELECT count(*) FROM mi_ep_scan_log s WHERE s.ticker=l.ticker AND s.scan_date=l.d::date) n_rows_any,
  (SELECT count(*) FROM mi_ep_scan_log s WHERE s.ticker=l.ticker AND s.scan_date=l.d::date AND s.rank_by_gap IS NOT NULL
      AND (s.scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30') n_ranked_preopen,
  (SELECT to_char(min(s.scan_time_et) AT TIME ZONE 'America/New_York','HH24:MI') FROM mi_ep_scan_log s WHERE s.ticker=l.ticker AND s.scan_date=l.d::date) first_any,
  (SELECT to_char(min(s.scan_time_et) AT TIME ZONE 'America/New_York','HH24:MI') FROM mi_ep_scan_log s WHERE s.ticker=l.ticker AND s.scan_date=l.d::date AND s.rank_by_gap IS NOT NULL) first_ranked,
  (SELECT to_char(max(s.scan_time_et) AT TIME ZONE 'America/New_York','HH24:MI') FROM mi_ep_scan_log s WHERE s.ticker=l.ticker AND s.scan_date=l.d::date AND s.rank_by_gap IS NOT NULL
      AND (s.scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30') last_ranked_preopen,
  (SELECT s.rank_by_gap FROM mi_ep_scan_log s JOIN lt ON lt.scan_date=s.scan_date AND lt.t=s.scan_time_et WHERE s.ticker=l.ticker AND s.scan_date=l.d::date) rank_at_day_last_tick,
  (SELECT max(s.gap_pct) FROM mi_ep_scan_log s WHERE s.ticker=l.ticker AND s.scan_date=l.d::date AND (s.scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30') max_preopen_gap,
  (SELECT left(string_agg(DISTINCT coalesce(s.reject_stage,'-')||':'||left(coalesce(s.filter_reason,''),35), ' ; '),200) FROM mi_ep_scan_log s WHERE s.ticker=l.ticker AND s.scan_date=l.d::date
      AND (s.scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30') preopen_reasons
FROM lab l ORDER BY l.d, l.ticker;
\echo '### V12d ADV/RS at P for 7 rows not checked before (P = latest complete score_date <= d-1, the production rule inlined)'
WITH pick(ticker, d) AS (VALUES ('BLZE',DATE '2026-08-04'),('INSP',DATE '2026-08-04'),('CHPT',DATE '2026-09-03'),('QURE',DATE '2026-05-29'),
   ('BFLY',DATE '2026-06-18'),('SMHI',DATE '2026-07-30'),('MRAM',DATE '2026-05-13'),('ARM',DATE '2026-05-06')),
pp AS (SELECT p.ticker, p.d,
  (SELECT counts.score_date FROM (SELECT score_date, COUNT(*) AS n FROM mi_stock_scores WHERE score_date <= p.d - 1 GROUP BY score_date) counts
    WHERE counts.n >= 0.5 * (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY n) FROM (
        SELECT COUNT(*) AS n FROM mi_stock_scores WHERE score_date <= p.d - 1 GROUP BY score_date ORDER BY score_date DESC LIMIT 10) recent)
    ORDER BY counts.score_date DESC LIMIT 1) AS p_date FROM pick p),
lt AS (SELECT scan_date, max(scan_time_et) t FROM mi_ep_scan_log WHERE rank_by_gap IS NOT NULL
        AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30' AND scan_date IN (SELECT d FROM pick) GROUP BY 1)
SELECT pp.ticker, pp.d, pp.p_date, s.adv_20, s.rs_composite, s.rs_rank, l.prev_close, s.adv_20 * l.prev_close adv_dollar,
       l.today_volume, l.current_price, l.rel_volume, l.adv logged_adv, l.adv_source, l.pm_rvol, l.in_active_theme, l.gap_pct,
       s0.adv_20 adv20_on_d
  FROM pp LEFT JOIN mi_stock_scores s ON s.ticker=pp.ticker AND s.score_date=pp.p_date
  LEFT JOIN mi_stock_scores s0 ON s0.ticker=pp.ticker AND s0.score_date=pp.d
  LEFT JOIN lt ON lt.scan_date = pp.d
  LEFT JOIN mi_ep_scan_log l ON l.ticker=pp.ticker AND l.scan_date=pp.d AND l.scan_time_et = lt.t
 ORDER BY pp.d, pp.ticker;
\echo '### V12e shortlist shadow on 10-05 09:25: logged adv/adv_source per name at sort time (should be pending/empty pre-open)'
SELECT ticker, rank_by_prescore, rank_by_gap, adv, adv_source, in_active_theme
  FROM mi_ep_shortlist_shadow
 WHERE scan_date='2026-10-05' AND to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI')='09:25' ORDER BY rank_by_prescore;
