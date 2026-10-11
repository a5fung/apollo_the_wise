-- #698 re-fire check — follow-up (NEW questions raised by q1_refire.out; not a re-read).
-- READ-ONLY. Captured ONCE on 2026-10-10 into q2_followup.out.
\echo === F1 trades 407 / 410 / 417 (partial_exit_sell_placed rows but no partial_exit order row in q1 Q4)
SELECT id, ticker, account_mode, signal_type, status, entry_shares, remaining_shares, partial_taken, breakeven_active, entry_price, hard_stop, stop_price,
       filled_at, closed_at, skip_reason, exit_rule, exits::text
FROM mi_live_trades WHERE id IN (407, 410, 417) ORDER BY id;

\echo === F2 every order row for those trades
SELECT trade_id, alpaca_order_id, side, order_type, qty, stop_price, limit_price, status, purpose, exit_reason, raw_response->>'order_class' AS cls, submitted_at, filled_at, cancelled_at
FROM mi_live_orders WHERE trade_id IN (407, 410, 417) ORDER BY trade_id, submitted_at;

\echo === F3 every audit row for those trades (by detail trade_id or ticker in summary), 2026-10-01 onward
WITH t AS (SELECT id, ticker FROM mi_live_trades WHERE id IN (407, 410, 417))
SELECT a.created_at, a.event_type, left(a.summary, 200) AS summary
FROM mi_audit_log a
WHERE a.created_at >= '2026-10-01'
  AND ( (left(btrim(a.detail),1) = '{' AND (a.detail::jsonb->>'trade_id') IN (SELECT id::text FROM t))
        OR a.summary ~ ('^(' || (SELECT string_agg(ticker, '|') FROM t) || ')[: ]') )
ORDER BY a.created_at;

\echo === F4 the two oco_parent_cancelled_unfilled rows, in full
SELECT created_at, event_type, summary, detail FROM mi_audit_log WHERE event_type = 'oco_parent_cancelled_unfilled' ORDER BY created_at;

\echo === F5 GOOGL 56 / TEAM 57 — the FIRST sell orders (82ebdc29 / ce35d7a8) that q1 Q4 did not list: any order row? any audit row naming them?
SELECT 'order_row' AS src, alpaca_order_id, status, purpose, qty, submitted_at::text AS at_, '' AS summary
FROM mi_live_orders WHERE alpaca_order_id LIKE '82ebdc29%' OR alpaca_order_id LIKE 'ce35d7a8%'
UNION ALL
SELECT 'audit', '', event_type, '', NULL, created_at::text, left(summary, 200)
FROM mi_audit_log WHERE summary LIKE '%82ebdc29%' OR summary LIKE '%ce35d7a8%' OR detail LIKE '%82ebdc29%' OR detail LIKE '%ce35d7a8%'
ORDER BY at_;

\echo === F6 the 05-05/05-06 GOOGL + TEAM full audit timeline (what happened between the two sell placements)
SELECT created_at, event_type, left(summary, 220) AS summary FROM mi_audit_log
WHERE created_at BETWEEN '2026-05-05 20:00' AND '2026-05-06 14:00'
  AND (summary LIKE 'GOOGL%' OR summary LIKE 'TEAM%' OR detail LIKE '%"trade_id": 56%' OR detail LIKE '%"trade_id": 57%')
ORDER BY created_at;

\echo === F7 how many partials since resting mode went live (08-10) ran each order shape, and how each one's breakeven step ended
SELECT event_type, count(*) AS n FROM mi_audit_log
WHERE created_at >= '2026-08-10'
  AND event_type IN ('partial_exit_sell_placed','partial_exit_breakeven_armed','partial_exit_breakeven_deferred','partial_exit_breakeven_unverified','partial_exit_breakeven_unverifiable','partial_exit_oco_fallback','breakeven_armed','breakeven_arm_noop','breakeven_arm_rejected','breakeven_arm_failed','breakeven_arm_skipped')
GROUP BY 1 ORDER BY 1;
