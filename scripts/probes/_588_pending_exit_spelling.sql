-- #588 pass 3 — does the cancelled/canceled spelling split reach the exit-order
-- filter, and does the invariant survive a still-resting carve-out? READ-ONLY.
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;

\echo ===Q1_ORDER_STATUS_BY_PURPOSE===
SELECT COALESCE(purpose,'(null)') AS purpose, status, COUNT(*) AS n
FROM mi_live_orders GROUP BY 1,2 ORDER BY 1,2;

\echo ===Q2_INVARIANT_WITH_PENDING_EXIT_EXCLUSION_NO_DATE_BOUND===
SELECT t.id, t.ticker, t.account_mode, t.alert_date, t.entry_shares,
       COALESCE((SELECT SUM((x->>'shares')::numeric)
                   FROM jsonb_array_elements(t.exits) x), 0) AS exit_shares
FROM mi_live_trades t
WHERE t.status = 'closed'
  AND COALESCE(t.entry_attempt, 1) = 1
  AND t.closed_at IS NOT NULL
  AND jsonb_array_length(COALESCE(t.exits, '[]'::jsonb)) > 0
  AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(t.exits) x WHERE NOT (x ? 'shares'))
  AND NOT EXISTS (
        SELECT 1 FROM mi_live_orders o
        WHERE o.trade_id = t.id
          AND o.purpose IN ('partial_exit', 'full_exit')
          AND o.status NOT IN ('filled', 'cancelled', 'canceled', 'rejected', 'expired')
  )
  AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric)
                      FROM jsonb_array_elements(t.exits) x), 0) - t.entry_shares) > 0.001
ORDER BY t.closed_at DESC;

\echo ===Q3_OPEN_EXIT_ORDERS_RIGHT_NOW===
SELECT trade_id, ticker, purpose, qty, filled_qty, status
FROM mi_live_orders
WHERE purpose IN ('partial_exit','full_exit')
  AND status NOT IN ('filled','cancelled','canceled','rejected','expired')
ORDER BY trade_id;
