-- Lattice-admission consistency fix (2026-08-22). READ-ONLY capture, one pull read many.
-- Measures the routine-gap<12 post-grade filter + pm-shares R6 carve-out, before/after
-- the acting-grade (catalyst_tier_lattice) consistency change. Run:
--   ssh apollo@87.99.134.162 "docker exec apollo-postgres psql -U apollo -d apollo" < this
\echo ===Q1_ROUTINE_KILL_VOLUME
SELECT 'all' w, count(*) ticks, count(DISTINCT (scan_date::text||ticker)) tdays, count(DISTINCT scan_date) days
FROM mi_ep_scan_log WHERE filter_reason LIKE 'routine catalyst%'
UNION ALL
SELECT '60d', count(*), count(DISTINCT (scan_date::text||ticker)), count(DISTINCT scan_date)
FROM mi_ep_scan_log WHERE filter_reason LIKE 'routine catalyst%' AND scan_date >= CURRENT_DATE - 60;
\echo ===Q1B_SCAN_DAYS
SELECT 'all' w, count(DISTINCT scan_date) days FROM mi_ep_scan_log
UNION ALL SELECT '60d', count(DISTINCT scan_date) FROM mi_ep_scan_log WHERE scan_date >= CURRENT_DATE - 60;
\echo ===Q2_TERMINAL_KILLS
WITH k AS (
  SELECT DISTINCT scan_date, ticker FROM mi_ep_scan_log WHERE filter_reason LIKE 'routine catalyst%'
), a AS (SELECT DISTINCT alert_date, ticker FROM mi_ep_alerts)
SELECT 'all' w, count(*) FILTER (WHERE a.ticker IS NULL) terminal, count(*) total
FROM k LEFT JOIN a ON a.alert_date=k.scan_date AND a.ticker=k.ticker
UNION ALL
SELECT '60d', count(*) FILTER (WHERE a.ticker IS NULL), count(*)
FROM k LEFT JOIN a ON a.alert_date=k.scan_date AND a.ticker=k.ticker
WHERE k.scan_date >= CURRENT_DATE - 60;
\echo ===Q3_KILLED_DETAIL_60D
WITH k AS (
  SELECT scan_date, ticker, round(min(gap_pct)::numeric,1) gmin, round(max(gap_pct)::numeric,1) gmax,
         max(adv) adv, max(prev_close) pc, max(rel_volume) rv, max(projected_vol_multiple) pv, count(*) ticks
  FROM mi_ep_scan_log WHERE filter_reason LIKE 'routine catalyst%' AND scan_date >= CURRENT_DATE - 60
  GROUP BY 1,2)
SELECT k.scan_date, k.ticker, k.gmin, k.gmax, k.ticks,
  round((k.adv*k.pc)::numeric/1e6,1) adv_musd, k.rv, k.pv,
  (a.ticker IS NOT NULL) alerted_same_day
FROM k LEFT JOIN (SELECT DISTINCT alert_date, ticker FROM mi_ep_alerts) a
  ON a.alert_date=k.scan_date AND a.ticker=k.ticker
ORDER BY 1,2;
\echo ===Q4_MEMBER_DAYS
SELECT scan_date, ticker,
  COALESCE(filter_reason,'(scored '||COALESCE(score_tier,'no-tier')||' '||COALESCE(round(ep_score::numeric,0)::text,'-')||')') why,
  count(*) n, round(min(gap_pct)::numeric,1) gmin, round(max(gap_pct)::numeric,1) gmax
FROM mi_ep_scan_log
WHERE (ticker, scan_date) IN (VALUES
  ('MRNA','2026-08-19'::date),('MU','2026-04-08'::date),('UMC','2026-04-17'::date),
  ('STRL','2026-04-08'::date),('MRVL','2026-03-31'::date),('ASX','2026-04-08'::date),
  ('SNDK','2026-04-08'::date),('SNOW','2026-05-07'::date),('ALGM','2026-04-08'::date),
  ('NBIS','2026-04-08'::date),('AMKR','2026-04-08'::date),('AEHR','2026-03-31'::date),
  ('TDIC','2026-05-12'::date),('UMC','2026-05-06'::date),('FLY','2026-03-12'::date),
  ('BE','2026-04-08'::date),('USAR','2026-04-08'::date),('QCOM','2026-04-24'::date),
  ('QBTS','2026-04-08'::date),('AMD','2026-04-24'::date),('HUT','2026-04-08'::date),
  ('QURE','2026-05-29'::date),('ARM','2026-05-06'::date),('SMTC','2026-03-30'::date),
  ('IREN','2026-04-08'::date),('APLD','2026-04-08'::date),('INTC','2026-04-24'::date))
GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo ===Q5_PM_SHARES_KILLS
SELECT 'all' w, count(DISTINCT (scan_date::text||ticker)) tdays FROM mi_ep_scan_log WHERE filter_reason LIKE 'pre-mkt volume%'
UNION ALL SELECT '60d', count(DISTINCT (scan_date::text||ticker)) FROM mi_ep_scan_log WHERE filter_reason LIKE 'pre-mkt volume%' AND scan_date >= CURRENT_DATE - 60;
\echo ===Q6_PM_SHARES_GAP10_60D
WITH k AS (SELECT scan_date, ticker, max(gap_pct) gmax FROM mi_ep_scan_log
  WHERE filter_reason LIKE 'pre-mkt volume%' AND scan_date >= CURRENT_DATE - 60 GROUP BY 1,2)
SELECT count(*) FILTER (WHERE gmax>=10) ge10, count(*) total,
  count(*) FILTER (WHERE gmax>=10 AND a.ticker IS NULL) ge10_terminal
FROM k LEFT JOIN (SELECT DISTINCT alert_date,ticker FROM mi_ep_alerts) a
  ON a.alert_date=k.scan_date AND a.ticker=k.ticker;
\echo ===Q7_HIGH_PER_DAY_60D
SELECT count(*) FILTER (WHERE score_tier='HIGH') highs, count(*) alerts, count(DISTINCT alert_date) days
FROM mi_ep_alerts WHERE alert_date >= CURRENT_DATE - 60;
\echo ===Q8_ROUTINE_ALERTS_GAP_60D
SELECT count(*) n, count(*) FILTER (WHERE gap_pct < 12) lt12
FROM mi_ep_alerts WHERE catalyst_quality='routine' AND alert_date >= CURRENT_DATE - 60;
