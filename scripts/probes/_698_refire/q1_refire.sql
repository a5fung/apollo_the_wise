-- #698 Known limitation 7 — "+8R partial re-fires after its OCO slice stops out": has it ever happened?
-- READ-ONLY (SELECT only). Captured ONCE on 2026-10-10 into q1_refire.out; read the file, never re-run.
\echo === Q1 toggles (order shape + breakeven + depth + leg-safe)
SELECT safeguard, account_mode, state, last_transition_at
FROM mi_safeguard_state
WHERE safeguard IN ('profit_take_resting_limit','profit_take_oco','breakeven_at_broker','partial_exit_leg_safe','magna53_depth_exit')
ORDER BY 1,2;

\echo === Q2 strategies (level + arm)
SELECT strategy_id, signal_type, phase, enabled, live_real_enabled, profit_trigger_r, breakeven_arm_r FROM mi_strategies ORDER BY 1;

\echo === Q3 per-trade counts of the partial-exit events, ALL TIME (any count >1 on fired / sell_placed / committed = a candidate double sale)
WITH ev AS (
  SELECT event_type, created_at,
         CASE WHEN left(btrim(detail),1) = '{' THEN detail::jsonb END AS d
  FROM mi_audit_log
  WHERE event_type IN ('profit_trigger_fired','profit_trigger_failed','partial_exit_started','partial_exit_sell_placed','partial_exit_committed','partial_exit_aborted')
)
SELECT (d->>'trade_id')::int AS trade_id,
       count(*) FILTER (WHERE event_type='profit_trigger_fired')     AS fired,
       count(*) FILTER (WHERE event_type='profit_trigger_failed')    AS failed,
       count(*) FILTER (WHERE event_type='partial_exit_started')     AS started,
       count(*) FILTER (WHERE event_type='partial_exit_sell_placed') AS sell_placed,
       count(*) FILTER (WHERE event_type='partial_exit_committed')   AS committed,
       count(*) FILTER (WHERE event_type='partial_exit_aborted')     AS aborted,
       min(created_at)::date AS first, max(created_at)::date AS last
FROM ev WHERE d IS NOT NULL AND (d->>'trade_id') ~ '^[0-9]+$'
GROUP BY 1 ORDER BY 1;

\echo === Q4 every partial_exit order ever (order class, status, timings) with its trade
SELECT o.trade_id, t.ticker, t.account_mode, t.signal_type, t.entry_shares, t.entry_price, t.hard_stop, t.stop_price AS trade_stop_now,
       t.status AS trade_status, t.partial_taken, t.remaining_shares,
       o.alpaca_order_id, o.order_type, o.qty, o.limit_price, o.status AS ord_status,
       o.raw_response->>'order_class' AS cls, o.submitted_at, o.filled_at, o.cancelled_at, o.filled_qty
FROM mi_live_orders o JOIN mi_live_trades t ON t.id = o.trade_id
WHERE o.purpose = 'partial_exit'
ORDER BY o.submitted_at;

\echo === Q5 OCO parents -> their sibling stop legs (leg row status = did the slice exit at its own stop?)
WITH parents AS (
  SELECT o.trade_id, o.alpaca_order_id AS parent_id, o.status AS parent_status, o.qty AS parent_qty, o.limit_price,
         o.submitted_at, l->>'id' AS leg_id
  FROM mi_live_orders o
  CROSS JOIN LATERAL jsonb_array_elements(COALESCE(o.raw_response->'legs','[]'::jsonb)) l
  WHERE o.purpose = 'partial_exit' AND o.raw_response->>'order_class' = 'oco'
)
SELECT p.trade_id, t.ticker, t.account_mode, p.parent_id, p.parent_status, p.parent_qty, p.limit_price, p.submitted_at,
       p.leg_id, lg.status AS leg_status, lg.qty AS leg_qty, lg.stop_price AS leg_stop, lg.filled_at AS leg_filled_at, lg.purpose AS leg_purpose,
       t.entry_price, t.stop_price AS trade_stop_now, t.status AS trade_status, t.partial_taken, t.remaining_shares
FROM parents p
JOIN mi_live_trades t ON t.id = p.trade_id
LEFT JOIN mi_live_orders lg ON lg.alpaca_order_id = p.leg_id
ORDER BY p.submitted_at;

\echo === Q6 every FILLED stop_loss order whose qty < the trade's entry_shares (a partial-quantity stop fill — the OCO leg or a reduced main stop)
SELECT o.trade_id, t.ticker, t.account_mode, o.alpaca_order_id, o.qty, o.stop_price, o.status, o.filled_at, o.filled_qty, o.filled_avg_price,
       t.entry_shares, t.entry_price, t.status AS trade_status, t.partial_taken, t.remaining_shares, t.closed_at
FROM mi_live_orders o JOIN mi_live_trades t ON t.id = o.trade_id
WHERE o.purpose = 'stop_loss' AND o.status = 'filled' AND o.qty < t.entry_shares
ORDER BY o.filled_at;

\echo === Q7 audit event counts, ALL TIME, for the OCO-unwind / breakeven-degrade / clamp paths
SELECT event_type, count(*) AS n, min(created_at)::date AS first, max(created_at)::date AS last
FROM mi_audit_log
WHERE event_type IN ('oco_parent_cancelled_sibling_filled','oco_parent_cancelled_unfilled',
                     'partial_exit_breakeven_deferred','partial_exit_breakeven_unverified','partial_exit_breakeven_unverifiable',
                     'partial_exit_breakeven_armed','partial_exit_oco_fallback','partial_exit_reprotect_failed',
                     'remaining_shares_clamped','breakeven_armed','breakeven_arm_rejected','breakeven_arm_failed',
                     'breakeven_arm_noop','breakeven_arm_skipped','breakeven_arm_unverified',
                     'stop_exit_committed','partial_exit_sell_placed','partial_exit_committed','profit_trigger_fired')
GROUP BY 1 ORDER BY 1;

\echo === Q8 stop_exit_committed rows that left shares OPEN (a partial-quantity stop fill), ALL TIME
SELECT created_at, summary FROM mi_audit_log
WHERE event_type = 'stop_exit_committed' AND summary ILIKE '%remain%'
ORDER BY created_at;

\echo === Q9 trades whose exits[] carry >= 2 partial_profit entries, or any partial_profit + stop_hit mix (ALL TIME)
SELECT t.id, t.ticker, t.account_mode, t.signal_type, t.entry_shares, t.remaining_shares, t.partial_taken, t.status, t.filled_at::date AS filled, t.closed_at::date AS closed,
       (SELECT count(*) FROM jsonb_array_elements(COALESCE(t.exits::jsonb,'[]'::jsonb)) e WHERE e->>'reason'='partial_profit') AS n_partials,
       (SELECT count(*) FROM jsonb_array_elements(COALESCE(t.exits::jsonb,'[]'::jsonb)) e WHERE e->>'reason'='stop_hit') AS n_stops,
       (SELECT string_agg((e->>'reason')||':'||(e->>'shares')||'@'||(e->>'price'), ' | ' ORDER BY e->>'time') FROM jsonb_array_elements(COALESCE(t.exits::jsonb,'[]'::jsonb)) e) AS exits_seq
FROM mi_live_trades t
WHERE t.partial_taken = TRUE OR t.id IN (SELECT trade_id FROM mi_live_orders WHERE purpose='partial_exit')
ORDER BY t.id;

\echo === Q10 timeline for EVERY trade that ever had a partial_exit order (what the stops were, and what happened next)
WITH tids AS (SELECT DISTINCT trade_id FROM mi_live_orders WHERE purpose='partial_exit'),
ev AS (
  SELECT created_at, event_type, summary,
         CASE WHEN left(btrim(detail),1) = '{' THEN detail::jsonb END AS d
  FROM mi_audit_log
  WHERE event_type IN ('profit_trigger_fired','profit_trigger_failed','partial_exit_started','partial_exit_sell_placed','partial_exit_committed','partial_exit_aborted',
                       'partial_exit_breakeven_deferred','partial_exit_breakeven_unverified','partial_exit_breakeven_unverifiable','partial_exit_breakeven_armed',
                       'oco_parent_cancelled_sibling_filled','oco_parent_cancelled_unfilled','stop_exit_committed','remaining_shares_clamped',
                       'breakeven_armed','breakeven_arm_rejected','breakeven_arm_failed','breakeven_arm_noop','breakeven_arm_unverified',
                       'stop_replaced','stop_update_aborted','stop_updated','trail_stop_updated','full_exit_committed','partial_exit_sell_failed')
)
SELECT (d->>'trade_id')::int AS trade_id, created_at, event_type, left(summary, 170) AS summary,
       d->>'stop_price' AS d_stop, d->>'oco_stop_price' AS d_oco_stop, d->>'new_remaining' AS d_new_rem, d->>'shares' AS d_shares
FROM ev WHERE d IS NOT NULL AND (d->>'trade_id') ~ '^[0-9]+$' AND (d->>'trade_id')::int IN (SELECT trade_id FROM tids)
ORDER BY 1, 2;

\echo === Q11 depth-rule trades (exit_rule stamped) and the current open book
SELECT id, ticker, account_mode, signal_type, status, entry_shares, remaining_shares, partial_taken, breakeven_active, exit_rule,
       entry_price, hard_stop, stop_price, stop_order_id, highest_price_seen, filled_at::date AS filled
FROM mi_live_trades
WHERE exit_rule IS NOT NULL OR status IN ('filled','stop_processing','filling')
ORDER BY filled_at;

\echo === Q12 for each OPEN trade: MAX(high) since fill vs the +8R target (would the poll select it right now?)
SELECT t.id, t.ticker, t.account_mode, t.signal_type, t.remaining_shares, t.partial_taken,
       round((t.entry_price + 8*(t.entry_price - t.orb_low))::numeric,2) AS tgt8r,
       (SELECT max(high) FROM mi_intraday_bars b WHERE b.ticker=t.ticker AND b.bar_time >= t.filled_at) AS max_high_since_fill
FROM mi_live_trades t WHERE t.status='filled' AND t.remaining_shares > 0 ORDER BY t.id;
