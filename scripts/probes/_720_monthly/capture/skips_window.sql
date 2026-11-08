SET default_transaction_read_only = on;
-- #720 §3 selection: every mi_live_trades row that was NOT filled (skips, cancels) since the first window start — so a name he labelled reads traded / skipped (reason) / never alerted.
\copy (SELECT id, ticker, alert_date, account_mode, signal_type, status, skip_reason, ep_score, created_at FROM mi_live_trades WHERE filled_at IS NULL AND alert_date >= DATE '2026-08-16' ORDER BY alert_date, ticker) TO STDOUT WITH CSV HEADER
