-- #312 Step A stop-condition (b) + baseline. READ-ONLY. Captured once 2026-10-10.
\echo === Q1 mi_pending_allocations: per alert_date arrival (created_at ET) vs 09:28 / 09:35, last 45 calendar days ===
\echo NOTE created_at is refreshed to NOW() on every UPSERT re-score, so it is the LAST write, not first arrival
SELECT alert_date,
       COUNT(*) AS rows_total,
       COUNT(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::time < TIME '09:28') AS last_write_before_0928,
       COUNT(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::time >= TIME '09:28'
                          AND (created_at AT TIME ZONE 'America/New_York')::time < TIME '09:35') AS last_write_0928_0935,
       COUNT(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::time >= TIME '09:35') AS last_write_after_0935,
       MIN((created_at AT TIME ZONE 'America/New_York')::time) AS earliest_et,
       MAX((created_at AT TIME ZONE 'America/New_York')::time) AS latest_et,
       COUNT(*) FILTER (WHERE shadow_rank IS NOT NULL) AS ranked_rows
FROM mi_pending_allocations
WHERE alert_date >= CURRENT_DATE - INTERVAL '45 days'
GROUP BY alert_date ORDER BY alert_date;

\echo === Q2 open positions NOW by account_mode x status (the allocator counts ALL modes; the safeguard counts per mode) ===
SELECT account_mode, status, COUNT(*) AS n, MIN(alert_date) AS oldest_alert, MAX(alert_date) AS newest_alert
FROM mi_live_trades
WHERE status IN ('filled','order_placed','confirmed')
GROUP BY account_mode, status ORDER BY account_mode, status;

\echo === Q3 allocator audit rows, last 45 days: run time ET + summary (baseline: every row at 09:35) ===
SELECT (created_at AT TIME ZONE 'America/New_York') AS et, summary
FROM mi_audit_log
WHERE event_type = 'unified_allocation_decided'
  AND created_at > NOW() - INTERVAL '45 days'
ORDER BY created_at;

\echo === Q4 entries that became OPEN (confirmed_at) in the last 45 days: confirmed/filled times ET per row, by account_mode ===
SELECT alert_date, ticker, account_mode, status,
       (confirmed_at AT TIME ZONE 'America/New_York')::time AS confirmed_et,
       (filled_at AT TIME ZONE 'America/New_York')::time AS filled_et,
       (created_at AT TIME ZONE 'America/New_York')::time AS created_et,
       (confirmed_at AT TIME ZONE 'America/New_York')::date = alert_date AS confirmed_on_alert_date
FROM mi_live_trades
WHERE alert_date >= CURRENT_DATE - INTERVAL '45 days'
  AND confirmed_at IS NOT NULL
ORDER BY alert_date, confirmed_at;

\echo === Q5 columns of mi_ep_scan_log / mi_ep_alerts (to find a FIRST-arrival timestamp) ===
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('mi_ep_scan_log','mi_ep_alerts')
  AND (column_name LIKE '%time%' OR column_name LIKE '%_at' OR column_name IN ('ticker','alert_date','scan_date','score_tier','tier'))
ORDER BY table_name, ordinal_position;

\echo === Q6 open-position count the allocator would compute today vs per-mode ===
SELECT COUNT(*) AS all_modes,
       COUNT(*) FILTER (WHERE account_mode='live') AS live_only,
       COUNT(*) FILTER (WHERE account_mode='paper') AS paper_only
FROM mi_live_trades WHERE status IN ('filled','order_placed','confirmed');
