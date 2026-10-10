\echo === days
WITH d AS (SELECT DISTINCT scan_date FROM mi_ep_scan_log WHERE scan_date < '2026-10-10' ORDER BY scan_date DESC LIMIT 30)
SELECT min(scan_date), max(scan_date), count(*) FROM d;
\echo === stage x per-day (distinct ticker-days where that stage appears)
WITH d AS (SELECT DISTINCT scan_date FROM mi_ep_scan_log WHERE scan_date < '2026-10-10' ORDER BY scan_date DESC LIMIT 30)
SELECT reject_stage, count(DISTINCT (scan_date,ticker)) td, count(*) rows FROM mi_ep_scan_log WHERE scan_date IN (SELECT scan_date FROM d) GROUP BY 1 ORDER BY 2 DESC;
\echo === mcap filter reason sample
WITH d AS (SELECT DISTINCT scan_date FROM mi_ep_scan_log WHERE scan_date < '2026-10-10' ORDER BY scan_date DESC LIMIT 30)
SELECT left(filter_reason,60) r, count(DISTINCT (scan_date,ticker)) FROM mi_ep_scan_log WHERE scan_date IN (SELECT scan_date FROM d) AND reject_stage='quality_filter' GROUP BY 1 ORDER BY 2 DESC LIMIT 15;
\echo === graded ticker-days per day (llm_catalyst_quality not null)
WITH d AS (SELECT DISTINCT scan_date FROM mi_ep_scan_log WHERE scan_date < '2026-10-10' ORDER BY scan_date DESC LIMIT 30)
SELECT scan_date, count(DISTINCT ticker) FILTER (WHERE llm_catalyst_quality IS NOT NULL) graded,
 count(DISTINCT ticker) FILTER (WHERE reject_stage='quality_filter' AND filter_reason ILIKE '%mcap%') mcap_rej,
 count(DISTINCT ticker) all_names
FROM mi_ep_scan_log WHERE scan_date IN (SELECT scan_date FROM d) GROUP BY 1 ORDER BY 1;
\echo === mi_market_caps coverage
SELECT count(*), count(market_cap), min(fetched_at), max(fetched_at) FROM mi_market_caps;
\echo === lowcap lane signals
SELECT count(*), count(DISTINCT signal_date) FROM mi_lowcap_lane_signals;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_lowcap_lane_signals' ORDER BY ordinal_position;
