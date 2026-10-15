\pset pager off
\echo === V7-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === V7-1 WFF 10-12 / MMEDV 10-13 / AIFA 10-06 post-open scan rows 09:30-09:40 (today_volume, gap)
SELECT scan_date, ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') t_et, minutes_since_open mso, reject_stage, round(gap_pct::numeric,1) gap, round(prev_close::numeric,2) pc, today_volume FROM mi_ep_scan_log WHERE ((scan_date='2026-10-12' AND ticker='WFF') OR (scan_date='2026-10-13' AND ticker='MMEDV') OR (scan_date='2026-10-06' AND ticker='AIFA')) AND (scan_time_et AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '09:40' ORDER BY scan_date, scan_time_et;
\echo === V7-2 their rolling-20 mean history (60 cal days before each date): n, max, p90; n<20 rows = no history
WITH t(ticker, sd) AS (VALUES ('WFF','2026-10-12'::date),('MMEDV','2026-10-13'::date),('AIFA','2026-10-06'::date)),
 d AS (SELECT c.ticker, t.sd, c.trade_date, c.volume FROM mi_daily_closes c JOIN t ON t.ticker=c.ticker WHERE c.trade_date >= t.sd - 124 AND c.trade_date < t.sd),
 r AS (SELECT ticker, sd, trade_date, avg(volume) OVER w m, count(*) OVER w n FROM d WINDOW w AS (PARTITION BY ticker ORDER BY trade_date ROWS 19 PRECEDING))
SELECT ticker, sd, count(*) FILTER (WHERE n=20 AND trade_date >= sd - 60) hist_n, round(max(m) FILTER (WHERE n=20 AND trade_date >= sd - 60)) max_mean20, (SELECT count(*) FROM d d2 WHERE d2.ticker=r.ticker) daily_rows FROM r GROUP BY 1,2 ORDER BY 2;
