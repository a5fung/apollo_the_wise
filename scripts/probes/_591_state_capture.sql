-- #591 — one read-only prod capture, 2026-08-24. NO WRITES (session forced read-only).
-- Run: ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" < this file
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;

\echo ===Q1_ETON_367_ORDERS===
-- Did get_pending_exit_qty actually SEE ETON's resting 5-share limit? It filters
-- purpose IN ('partial_exit','full_exit'); 61 orders in the book carry NULL purpose.
SELECT id, trade_id, ticker, purpose, qty, filled_qty, status, order_type,
       limit_price, stop_price, created_at
FROM mi_live_orders WHERE trade_id = 367 ORDER BY created_at, id;

\echo ===Q2_SPELLING_DELTA_ENUMERATION===
-- Every trade whose pending-exit qty CHANGES under the corrected spelling.
-- old = current filter (misses single-l 'canceled'); new = corrected.
SELECT o.trade_id, t.ticker, t.account_mode, t.alert_date, t.status AS trade_status,
       COALESCE(SUM(o.qty) FILTER (
           WHERE o.status NOT IN ('filled','cancelled','rejected','expired')), 0) AS old_held,
       COALESCE(SUM(o.qty) FILTER (
           WHERE o.status NOT IN ('filled','cancelled','canceled','rejected','expired')), 0) AS new_held
FROM mi_live_orders o
LEFT JOIN mi_live_trades t ON t.id = o.trade_id
WHERE o.purpose IN ('partial_exit','full_exit')
GROUP BY 1,2,3,4,5
HAVING COALESCE(SUM(o.qty) FILTER (
           WHERE o.status NOT IN ('filled','cancelled','rejected','expired')), 0)
    <> COALESCE(SUM(o.qty) FILTER (
           WHERE o.status NOT IN ('filled','cancelled','canceled','rejected','expired')), 0)
ORDER BY o.trade_id;

\echo ===Q2B_SPELLING_DELTA_COUNT===
SELECT COUNT(*) AS trades_affected FROM (
  SELECT o.trade_id
  FROM mi_live_orders o
  WHERE o.purpose IN ('partial_exit','full_exit')
  GROUP BY 1
  HAVING COALESCE(SUM(o.qty) FILTER (
             WHERE o.status NOT IN ('filled','cancelled','rejected','expired')), 0)
      <> COALESCE(SUM(o.qty) FILTER (
             WHERE o.status NOT IN ('filled','cancelled','canceled','rejected','expired')), 0)
) s;

\echo ===Q2C_EXIT_PURPOSE_ROWS_WITH_CANCELED_SPELLING===
-- The only rows that can move: purpose-labelled exit orders spelled 'canceled'.
SELECT purpose, status, COUNT(*) AS n, COALESCE(SUM(qty),0) AS total_qty
FROM mi_live_orders
WHERE purpose IN ('partial_exit','full_exit')
GROUP BY 1,2 ORDER BY 1,2;

\echo ===Q3_INVARIANT_WITHOUT_EXCLUSION_UNBOUNDED===
-- #588 invariant with the still-working-exit exclusion REMOVED, no date bound.
SELECT t.id, t.ticker, t.account_mode, t.alert_date, t.closed_at, t.entry_shares,
       COALESCE((SELECT SUM((x->>'shares')::numeric)
                   FROM jsonb_array_elements(t.exits) x), 0) AS exit_shares
FROM mi_live_trades t
WHERE t.status = 'closed'
  AND COALESCE(t.entry_attempt, 1) = 1
  AND t.closed_at IS NOT NULL
  AND jsonb_array_length(COALESCE(t.exits, '[]'::jsonb)) > 0
  AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(t.exits) x WHERE NOT (x ? 'shares'))
  AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric)
                      FROM jsonb_array_elements(t.exits) x), 0) - t.entry_shares) > 0.001
ORDER BY t.closed_at DESC;

\echo ===Q3B_INVARIANT_WITHOUT_EXCLUSION_SINCE_CUTOFF===
SELECT COUNT(*) AS n_since_cutoff FROM mi_live_trades t
WHERE t.status = 'closed'
  AND COALESCE(t.entry_attempt, 1) = 1
  AND t.closed_at IS NOT NULL
  AND (t.closed_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-24'
  AND jsonb_array_length(COALESCE(t.exits, '[]'::jsonb)) > 0
  AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(t.exits) x WHERE NOT (x ? 'shares'))
  AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric)
                      FROM jsonb_array_elements(t.exits) x), 0) - t.entry_shares) > 0.001;

\echo ===Q4_CLOSED_ROWS_WITH_A_WORKING_EXIT_ORDER===
-- The state the exclusion was tolerating: does any closed row have one TODAY?
SELECT t.id, t.ticker, t.account_mode, t.status, t.closed_at,
       o.id AS order_id, o.purpose, o.qty, o.status AS order_status
FROM mi_live_trades t
JOIN mi_live_orders o ON o.trade_id = t.id
WHERE t.status = 'closed'
  AND o.purpose IN ('partial_exit','full_exit')
  AND o.status NOT IN ('filled','cancelled','canceled','rejected','expired')
ORDER BY t.closed_at DESC;

\echo ===Q5_OPEN_ROWS_NOW===
SELECT id, ticker, account_mode, status, entry_shares, remaining_shares, stop_order_id, alert_date
FROM mi_live_trades
WHERE status NOT IN ('closed','skipped','expired','cancelled')
ORDER BY alert_date DESC LIMIT 30;
