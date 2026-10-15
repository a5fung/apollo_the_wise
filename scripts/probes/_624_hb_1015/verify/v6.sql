\pset pager off
\echo === V6-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === V6-1 GRML/AEHL 10-14 scan rows: every tick, today_volume, gap, stage (P15 free terms need gap>=15, pc>=5, vol pct>=90 at a post-open tick)
SELECT ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') t_et, minutes_since_open mso, reject_stage, round(gap_pct::numeric,1) gap, round(prev_close::numeric,2) pc, today_volume, prev_day_volume, round(rel_volume::numeric,2) rv, left(filter_reason,60) fr FROM mi_ep_scan_log WHERE scan_date='2026-10-14' AND ticker IN ('GRML','AEHL') AND (scan_time_et AT TIME ZONE 'America/New_York')::time BETWEEN '09:25' AND '10:00' ORDER BY ticker, scan_time_et;
\echo === V6-2 their rolling-20-day mean volume series (end-dates in the 60 calendar days before 10-14) = the P15 rank history: n, min, max
WITH d AS (SELECT ticker, trade_date, volume FROM mi_daily_closes WHERE ticker IN ('GRML','AEHL') AND trade_date >= '2026-10-14'::date - 124 AND trade_date < '2026-10-14'),
 r AS (SELECT ticker, trade_date, avg(volume) OVER w m, count(*) OVER w n FROM d WINDOW w AS (PARTITION BY ticker ORDER BY trade_date ROWS 19 PRECEDING))
SELECT ticker, count(*) hist_n, round(min(m)) min_mean20, round(max(m)) max_mean20, round(percentile_cont(0.9) WITHIN GROUP (ORDER BY m)) p90_mean20 FROM r WHERE n = 20 AND trade_date >= '2026-10-14'::date - 60 GROUP BY 1;
\echo === V6-3 their last 5 daily closes rows before 10-14 (is the daily table current for them)
SELECT ticker, trade_date, close, volume FROM mi_daily_closes WHERE ticker IN ('GRML','AEHL') AND trade_date >= '2026-10-06' ORDER BY ticker, trade_date;
