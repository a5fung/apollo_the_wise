SET default_transaction_read_only = on;
\echo == (1) live magna53 rows since 10-13 and their exit_rule
SELECT id, ticker, alert_date, account_mode, status, coalesce(exit_rule,'(none)') AS exit_rule FROM mi_live_trades
WHERE signal_type='magna53' AND account_mode='live' AND alert_date >= '2026-10-13' AND status NOT IN ('skipped','cancelled') ORDER BY id;
\echo == (2)(3) the zero clocks: rulings (iii) (i) (a) and the part-filled dead full-exit, since 10-04
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York')::timestamp(0) AS first_et FROM mi_audit_log
WHERE created_at >= '2026-10-04' AND event_type IN ('stop_breach_market_sale','stop_breach_sale_failed','stop_breach_sale_skipped',
  'restore_skipped_broker_flat','coverage_skipped_broker_flat','full_exit_dead_fill_booked','full_exit_dead_fill_duplicate')
GROUP BY 1 ORDER BY 1;
\echo == (4) depth sales since 10-12: vehicle, account, outcome
SELECT (created_at AT TIME ZONE 'America/New_York')::timestamp(0) et, event_type, left(summary,160) s, detail::jsonb->>'vehicle' vehicle, detail::jsonb->>'account_mode' acct
FROM mi_audit_log WHERE created_at >= '2026-10-12' AND event_type LIKE 'depth_open_sale%' ORDER BY created_at LIMIT 30;
