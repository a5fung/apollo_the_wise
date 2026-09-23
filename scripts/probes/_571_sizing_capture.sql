-- #571 position sizing — ONE prod capture (READ-ONLY), 2026-08-23.
-- Run: ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" < this file
-- Output: scripts/probes/_571_sizing_capture_out.psv. Never re-run to re-read.
\echo ===Q1_LIVE_BOOK===
SELECT id, ticker, alert_date, regime, status, orb_high, orb_low, atr_14,
       entry_price, entry_shares, stop_price, hard_stop, position_size, risk_dollars,
       remaining_shares, total_pnl, partial_taken, pnl_attribution, signal_type,
       to_char(filled_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS filled_et,
       to_char(closed_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS closed_et,
       skip_reason
FROM mi_live_trades WHERE account_mode='live' ORDER BY alert_date, id;
\echo ===Q2_EQUITY_SNAPSHOTS===
SELECT snapshot_date, equity FROM mi_account_equity_snapshots
WHERE account_mode='live' ORDER BY snapshot_date;
\echo ===Q3_REGIME===
SELECT regime_date, regime, vix, qqq_ema_bullish FROM mi_market_regime
WHERE regime_date >= '2026-06-15' ORDER BY regime_date;
\echo ===Q4_SIZING_FALLBACK_EVENTS===
SELECT to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS'), summary
FROM mi_audit_log WHERE event_type='sizing_regime_fallback' ORDER BY created_at;
\echo ===Q5_ORDERS===
SELECT o.trade_id, o.ticker, o.side, o.order_type, o.qty, o.filled_qty, o.filled_avg_price,
       o.status, o.purpose, o.stop_price, o.limit_price
FROM mi_live_orders o JOIN mi_live_trades t ON t.id=o.trade_id
WHERE t.account_mode='live' ORDER BY o.trade_id, o.id;
\echo ===Q6_STRATEGIES===
SELECT * FROM mi_strategies;
\echo ===Q7_SAFEGUARD_STATE===
SELECT safeguard, account_mode, state, last_drawdown_pct, updated_at FROM mi_safeguard_state;
\echo ===Q8_DRAWDOWN_EVENTS===
SELECT event_type, to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS')
FROM mi_audit_log WHERE event_type LIKE 'drawdown_%' AND created_at >= '2026-06-20'
ORDER BY created_at;
\echo ===Q9_PAPER_CONTEXT===
SELECT count(*) AS n_closed, round(avg(position_size)::numeric,0) AS avg_pos,
       round(max(position_size)::numeric,0) AS max_pos, round(avg(risk_dollars)::numeric,0) AS avg_risk
FROM mi_live_trades WHERE account_mode='paper' AND status='closed';
