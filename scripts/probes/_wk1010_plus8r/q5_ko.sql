\echo == KO partial rows (detail)
SELECT created_at, event_type, left(detail::text, 400) FROM mi_audit_log
WHERE event_type IN ('partial_exit_started','partial_exit_aborted') AND summary LIKE 'KO:%' ORDER BY created_at;
\echo == KO trade rows
SELECT id, ticker, signal_type, account_mode, status, entry_shares, remaining_shares, filled_at, partial_taken FROM mi_live_trades WHERE ticker='KO' ORDER BY id;
\echo == all open trades now
SELECT id, ticker, signal_type, account_mode, status, entry_shares, remaining_shares, partial_taken FROM mi_live_trades WHERE status IN ('filled','open','order_placed') ORDER BY id;
