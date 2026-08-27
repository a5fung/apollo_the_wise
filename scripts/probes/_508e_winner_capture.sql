-- first_live_winner review — ONE read-only prod capture, 2026-08-24. Never re-run to re-read.
-- Run: ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" < this file
\echo ===Q1_WINNER_TRADES===
SELECT id, ticker, alert_date, regime, status, orb_high, orb_low, atr_14, entry_price,
       entry_shares, stop_price, hard_stop, position_size, risk_dollars, risk_dollars_actual,
       remaining_shares, total_pnl, partial_taken, breakeven_active, hold_days,
       lowest_price_seen, highest_price_seen, pnl_attribution,
       to_char(filled_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS filled_et,
       to_char(closed_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS closed_et
FROM mi_live_trades WHERE id IN (307,367);
\echo ===Q2_EXIT_LEGS===
SELECT id, ticker, jsonb_pretty(exits) FROM mi_live_trades WHERE id IN (307,367);
\echo ===Q3_RUNNING_CLOSES===
SELECT id, ticker, jsonb_pretty(running_closes) FROM mi_live_trades WHERE id IN (307,367);
\echo ===Q4_ORDERS===
SELECT id, trade_id, ticker, side, order_type, qty, filled_qty, filled_avg_price, status,
       purpose, stop_price, limit_price,
       to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS created_et
FROM mi_live_orders WHERE trade_id IN (307,367) ORDER BY trade_id, id;
\echo ===Q5_SELL_RECORDS_ALL===
SELECT * FROM mi_sell_discipline_records ORDER BY trade_id;
\echo ===Q6_LIVE_BOOK_2R_ERA===
SELECT id, ticker, alert_date, status, orb_high, orb_low, entry_price, entry_shares,
       hard_stop, (entry_price-hard_stop) AS risk_per_share_at_stop,
       (orb_high-orb_low) AS orb_range, risk_dollars, total_pnl, partial_taken,
       to_char(filled_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS filled_et
FROM mi_live_trades WHERE account_mode='live' AND filled_at IS NOT NULL
ORDER BY filled_at;
\echo ===Q7_AUDIT_PARTIALS===
SELECT to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS et,
       event_type, summary FROM mi_audit_log
WHERE created_at >= '2026-08-04' AND (summary ILIKE '%PLTR%' OR summary ILIKE '%ETON%')
ORDER BY created_at;
