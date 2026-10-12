\echo === Q1 safeguard toggle rows
SELECT safeguard, account_mode, state, last_transition_at AT TIME ZONE 'America/New_York' AS trans_et, updated_at AT TIME ZONE 'America/New_York' AS upd_et FROM mi_safeguard_state WHERE safeguard='magna53_depth_exit' ORDER BY account_mode;

\echo === Q2 trade rows: created since 2026-10-12 00:00 ET OR open OR exit_rule not null OR depth_sell_pending_on not null
SELECT id, ticker, signal_type, account_mode, status, exit_rule, depth_sell_pending_on, alert_date, entry_attempt,
 created_at AT TIME ZONE 'America/New_York' AS created_et, filled_at AT TIME ZONE 'America/New_York' AS filled_et, closed_at AT TIME ZONE 'America/New_York' AS closed_et,
 entry_price, entry_shares, remaining_shares, stop_price, stop_order_id, total_pnl, skip_reason
FROM mi_live_trades
WHERE created_at >= (timestamp '2026-10-12 00:00' AT TIME ZONE 'America/New_York')
   OR status IN ('open','partial','active','filled','order_placed','pending','proposed')
   OR exit_rule IS NOT NULL OR depth_sell_pending_on IS NOT NULL
ORDER BY id DESC LIMIT 60;

\echo === Q2b status counts
SELECT status, account_mode, signal_type, count(*), count(exit_rule) AS stamped FROM mi_live_trades WHERE created_at >= now() - interval '30 days' GROUP BY 1,2,3 ORDER BY 2,3,1;

\echo === Q3 distinct audit event_types since 2026-10-12 09:30 ET with counts
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York') AS first_et, max(created_at AT TIME ZONE 'America/New_York') AS last_et
FROM mi_audit_log WHERE created_at >= (timestamp '2026-10-12 09:30' AT TIME ZONE 'America/New_York')
GROUP BY 1 ORDER BY 1;

\echo === Q4 job runs today for depth / live_position / drift / coverage
SELECT job_id, started_at AT TIME ZONE 'America/New_York' AS started_et, finished_at AT TIME ZONE 'America/New_York' AS fin_et, status, rows_written, left(coalesce(error_message,''),200) AS err
FROM mi_job_runs WHERE started_at >= (timestamp '2026-10-12 00:00' AT TIME ZONE 'America/New_York')
 AND (job_id ILIKE '%depth%' OR job_id ILIKE '%live_position%' OR job_id ILIKE '%drift%' OR job_id ILIKE '%live_rules%' OR job_id ILIKE '%coverage%' OR job_id ILIKE '%exit%')
ORDER BY started_at;
