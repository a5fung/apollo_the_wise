\pset pager off
\echo === V8-0 now ET
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') now_et;
\echo === V8-1 WFF 10-12 at the 09:30 tick: percentile of 7,351,633 in its rolling-20 mean history (P15 needs >= 90 with gap 20.3%)
WITH d AS (SELECT trade_date, volume FROM mi_daily_closes WHERE ticker='WFF' AND trade_date >= '2026-10-12'::date - 124 AND trade_date < '2026-10-12'),
 r AS (SELECT trade_date, avg(volume) OVER w m, count(*) OVER w n FROM d WINDOW w AS (ORDER BY trade_date ROWS 19 PRECEDING))
SELECT count(*) hist_n, count(*) FILTER (WHERE 7351633 > m) below, round(100.0*count(*) FILTER (WHERE 7351633 > m)/count(*),1) pct FROM r WHERE n=20 AND trade_date >= '2026-10-12'::date - 60;
\echo === V8-2 WFF cap anywhere we store it (scan log any date, P15 table, tinycap audit)
SELECT 'scanlog' src, max(scan_date)::text d, round((max(market_cap)/1e6)::numeric) mcap_m FROM mi_ep_scan_log WHERE ticker='WFF' AND market_cap IS NOT NULL
UNION ALL SELECT 'p15', max(scan_date)::text, round((max(market_cap)/1e6)::numeric) FROM mi_lowcap_lane_signals WHERE ticker='WFF'
UNION ALL SELECT 'tinycap_audit', max(to_char(created_at,'YYYY-MM-DD')), count(*) FROM mi_audit_log WHERE event_type='ep_tinycap_observed' AND summary LIKE 'WFF %';
