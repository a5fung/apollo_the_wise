CREATE TEMP TABLE d AS SELECT DISTINCT scan_date FROM mi_ep_scan_log WHERE scan_date < '2026-10-10' ORDER BY scan_date DESC LIMIT 30;
\echo === A mcap-rejected ticker-days (detail)
SELECT s.scan_date, s.ticker, round(max(s.market_cap)/1e6) cap_m, round(max(s.gap_pct)::numeric,1) maxgap, round(max(s.prev_close)::numeric,2) pc,
  min(to_char(s.scan_time_et AT TIME ZONE 'America/New_York','HH24:MI')) first_tick, count(*) ticks,
  bool_or(x.llm_catalyst_quality IS NOT NULL) graded_anyway,
  (SELECT count(*) FROM mi_lowcap_lane_signals l WHERE l.ticker=s.ticker AND l.scan_date=s.scan_date) lane_row
FROM mi_ep_scan_log s LEFT JOIN mi_ep_scan_log x ON x.scan_date=s.scan_date AND x.ticker=s.ticker AND x.llm_catalyst_quality IS NOT NULL
WHERE s.scan_date IN (SELECT scan_date FROM d) AND s.reject_stage='quality_filter' AND s.filter_reason ILIKE '%mcap_too_small%'
GROUP BY 1,2 ORDER BY 1,2;
\echo === A2 distinct tickers among mcap-rejected
SELECT count(DISTINCT ticker), count(DISTINCT (scan_date,ticker)) FROM mi_ep_scan_log WHERE scan_date IN (SELECT scan_date FROM d) AND reject_stage='quality_filter' AND filter_reason ILIKE '%mcap_too_small%';
\echo === B shortlist_cap ticker-days never reaching a later stage
SELECT s.scan_date, s.ticker, round(max(m.market_cap)/1e6) cap_m_now, round(max(s.gap_pct)::numeric,1) maxgap, max(s.extension_pct) ext, min(s.days_since_prior_alert) dsa,
  (SELECT string_agg(DISTINCT coalesce(y.reject_stage,'NULL'),',') FROM mi_ep_scan_log y WHERE y.scan_date=s.scan_date AND y.ticker=s.ticker) stages
FROM mi_ep_scan_log s LEFT JOIN mi_market_caps m ON m.ticker=s.ticker
WHERE s.scan_date IN (SELECT scan_date FROM d) AND s.reject_stage='shortlist_cap' GROUP BY 1,2 ORDER BY 1,2;
\echo === C board size per tick (candidates = rows not universe_floor/gap_floor) max per day
SELECT scan_date, max(n) max_board, round(avg(n),1) avg_board FROM (
 SELECT scan_date, scan_time_et, count(*) n FROM mi_ep_scan_log WHERE scan_date IN (SELECT scan_date FROM d) AND coalesce(reject_stage,'x') NOT IN ('universe_floor','gap_floor') GROUP BY 1,2) t GROUP BY 1 ORDER BY 1;
\echo === D graded ticker-days total + outcome stage among graded
SELECT count(DISTINCT (scan_date,ticker)) graded_td FROM mi_ep_scan_log WHERE scan_date IN (SELECT scan_date FROM d) AND llm_catalyst_quality IS NOT NULL;
SELECT count(*) alerts, count(DISTINCT (alert_date,ticker)) FROM mi_ep_alerts WHERE alert_date IN (SELECT scan_date FROM d) AND coalesce(source,'live') <> 'historical_scan';
SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_alerts' AND column_name IN ('source','score_tier','tier','account_mode','strategy_id');
