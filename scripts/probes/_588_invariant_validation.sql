-- #588 pass 2 — validate the new invariant SQL against prod + the orders join the
-- first pass missed (mi_live_orders has submitted_at, not created_at). READ-ONLY.
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;

\echo ===Q1_INVARIANT_AS_SHIPPED_CUTOFF_2026_08_24===
SELECT t.id, t.ticker, t.account_mode, t.alert_date, t.entry_shares,
       COALESCE((SELECT SUM((x->>'shares')::numeric)
                   FROM jsonb_array_elements(t.exits) x), 0) AS exit_shares
FROM mi_live_trades t
WHERE t.status = 'closed'
  AND COALESCE(t.entry_attempt, 1) = 1
  AND t.closed_at IS NOT NULL
  AND (t.closed_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-24'
  AND jsonb_array_length(COALESCE(t.exits, '[]'::jsonb)) > 0
  AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(t.exits) x WHERE NOT (x ? 'shares'))
  AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric)
                      FROM jsonb_array_elements(t.exits) x), 0) - t.entry_shares) > 0.001
ORDER BY t.closed_at DESC;

\echo ===Q2_SAME_INVARIANT_NO_DATE_BOUND===
SELECT t.id, t.ticker, t.account_mode, t.alert_date, t.entry_shares,
       COALESCE((SELECT SUM((x->>'shares')::numeric)
                   FROM jsonb_array_elements(t.exits) x), 0) AS exit_shares,
       t.total_pnl
FROM mi_live_trades t
WHERE t.status = 'closed'
  AND COALESCE(t.entry_attempt, 1) = 1
  AND t.closed_at IS NOT NULL
  AND jsonb_array_length(COALESCE(t.exits, '[]'::jsonb)) > 0
  AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(t.exits) x WHERE NOT (x ? 'shares'))
  AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric)
                      FROM jsonb_array_elements(t.exits) x), 0) - t.entry_shares) > 0.001
ORDER BY t.closed_at DESC;

\echo ===Q3_ETON_AND_FPS_ORDERS===
SELECT o.trade_id, o.ticker, o.purpose, o.side, o.order_type, o.qty, o.filled_qty,
       o.filled_avg_price, o.status,
       to_char(o.submitted_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS submitted_et,
       to_char(o.filled_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS filled_et
FROM mi_live_orders o
WHERE o.trade_id IN (367, 183, 107, 17)
ORDER BY o.trade_id, o.submitted_at;

\echo ===Q4_MULTI_ATTEMPT_ROWS_ARE_LEGIT===
SELECT id, ticker, account_mode, alert_date, entry_attempt, entry_shares,
       COALESCE((SELECT SUM((x->>'shares')::numeric) FROM jsonb_array_elements(exits) x),0) AS exit_shares
FROM mi_live_trades
WHERE id IN (34,57,81,82,120) ORDER BY id;
