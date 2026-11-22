SET default_transaction_read_only = on;
\echo === 1 all tier transitions since 2026-06-03 (live+paper)
SELECT created_at, event_type, left(summary,200) AS summary FROM mi_audit_log WHERE event_type LIKE 'drawdown%' AND created_at >= '2026-06-03' ORDER BY created_at;
\echo === 2 current breaker state
SELECT safeguard, account_mode, state, last_transition_at FROM mi_safeguard_state WHERE safeguard ILIKE '%drawdown%';
\echo === 3 live equity snapshots since 2026-10-01 (drawdown path, recovery vs -4% release)
SELECT snapshot_date, equity, cash, portfolio_value, source FROM mi_account_equity_snapshots WHERE account_mode='live' AND snapshot_date >= '2026-10-01' ORDER BY snapshot_date;
\echo === 4 live trade rows since the REDUCE entry (2026-11-12 21:12Z) - any status
SELECT id, ticker, alert_date, status, skip_reason, entry_price, entry_shares, stop_price, position_size, risk_dollars, risk_dollars_actual, total_pnl, remaining_shares, confirmed_at, created_at, closed_at FROM mi_live_trades WHERE account_mode='live' AND (created_at >= '2026-11-12 21:12+00' OR confirmed_at >= '2026-11-12 21:12+00' OR alert_date >= '2026-11-13') ORDER BY created_at;
\echo === 5 sizing audit rows since REDUCE (drawdown multiplier applied)
SELECT created_at, event_type, left(summary,260) AS summary FROM mi_audit_log WHERE event_type IN ('per_strategy_sizing_applied','sizing_multiplier_clamped') AND created_at >= '2026-11-12 21:12+00' ORDER BY created_at;
\echo === 6 skip/orb_skipped audit rows mentioning drawdown since REDUCE
SELECT created_at, event_type, left(summary,260) AS summary FROM mi_audit_log WHERE (summary ILIKE '%drawdown%' OR event_type ILIKE '%drawdown_breaker%') AND event_type NOT LIKE 'drawdown_%entered' AND event_type NOT LIKE 'drawdown_%released' AND created_at >= '2026-11-12 21:12+00' ORDER BY created_at;
\echo === 7 lifetime block:drawdown_breaker skips (any mode)
SELECT account_mode, count(*) FROM mi_live_trades WHERE skip_reason LIKE 'block:drawdown%' GROUP BY 1;
\echo === 8 OK/WATCH-tier live peers: last 15 live entries before REDUCE (sizing baseline)
SELECT id, ticker, alert_date, status, entry_price, entry_shares, position_size, risk_dollars, risk_dollars_actual, total_pnl, confirmed_at FROM mi_live_trades WHERE account_mode='live' AND entry_shares IS NOT NULL AND confirmed_at < '2026-11-12 21:12+00' ORDER BY confirmed_at DESC LIMIT 15;
\echo === 9 live candidates/alerts since 11-13 that did NOT become trades (counterfactual pool) - ep alerts
SELECT alert_date, count(*) FROM mi_live_trades WHERE account_mode='live' AND alert_date >= '2026-11-13' GROUP BY 1 ORDER BY 1;
