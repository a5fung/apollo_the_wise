-- #312 Step A stop-condition (b): FIRST arrival of each queue row (created_at is last-write). READ-ONLY. Captured once 2026-10-10.
\echo === Q7 per queue row: first HIGH/MODERATE scan-log time (ET) = first enqueue, last 45 days ===
WITH q AS (
  SELECT p.ticker, p.alert_date, p.composite_score, p.shadow_rank, p.shadow_allocated,
         (p.created_at AT TIME ZONE 'America/New_York')::time AS last_write_et,
         (SELECT MIN(s.scan_time_et AT TIME ZONE 'America/New_York')
            FROM mi_ep_scan_log s
           WHERE s.ticker = p.ticker AND s.scan_date = p.alert_date
             AND s.score_tier IN ('HIGH','MODERATE')) AS first_seen_et
  FROM mi_pending_allocations p
  WHERE p.alert_date >= CURRENT_DATE - INTERVAL '45 days'
)
SELECT alert_date, ticker, round(composite_score,1) AS composite, shadow_rank, shadow_allocated,
       first_seen_et::time AS first_seen_et, last_write_et,
       CASE WHEN first_seen_et::time < TIME '09:28' THEN 'by_0928'
            WHEN first_seen_et::time < TIME '09:35' THEN '0928_0935'
            WHEN first_seen_et IS NULL THEN 'no_scanlog'
            ELSE 'after_0935' END AS arrival
FROM q ORDER BY alert_date, first_seen_et;

\echo === Q8 per alert_date: rows first-seen by 09:28 vs later; would the 09:28 queue be non-empty? ===
WITH q AS (
  SELECT p.ticker, p.alert_date,
         (SELECT MIN(s.scan_time_et AT TIME ZONE 'America/New_York')
            FROM mi_ep_scan_log s
           WHERE s.ticker = p.ticker AND s.scan_date = p.alert_date
             AND s.score_tier IN ('HIGH','MODERATE')) AS first_seen_et
  FROM mi_pending_allocations p
  WHERE p.alert_date >= CURRENT_DATE - INTERVAL '45 days'
)
SELECT alert_date, COUNT(*) AS rows_total,
       COUNT(*) FILTER (WHERE first_seen_et::time < TIME '09:28') AS first_seen_by_0928,
       COUNT(*) FILTER (WHERE first_seen_et::time >= TIME '09:28' AND first_seen_et::time < TIME '09:35') AS first_seen_0928_0935,
       COUNT(*) FILTER (WHERE first_seen_et::time >= TIME '09:35') AS first_seen_after_0935,
       COUNT(*) FILTER (WHERE first_seen_et IS NULL) AS no_scanlog
FROM q GROUP BY alert_date ORDER BY alert_date;

\echo === Q9 paper rows in mi_live_trades, last 45 days (does the paper lane write here?) ===
SELECT account_mode, status, COUNT(*) AS n, MAX(alert_date) AS newest
FROM mi_live_trades
WHERE alert_date >= CURRENT_DATE - INTERVAL '45 days'
GROUP BY account_mode, status ORDER BY account_mode, status;

\echo === Q10 trading days in the window (distinct scan dates) for the denominator ===
SELECT COUNT(DISTINCT scan_date) AS scan_days, MIN(scan_date), MAX(scan_date)
FROM mi_ep_scan_log WHERE scan_date >= CURRENT_DATE - INTERVAL '45 days';
