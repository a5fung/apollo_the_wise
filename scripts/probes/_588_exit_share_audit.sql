-- #588 exit-share double-count audit — ONE read-only prod capture, 2026-08-24.
-- Run: ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" < this file
-- Captured once, read many. NO WRITES — session forced read-only below.
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;

\echo ===Q0_BOOK_SIZE===
SELECT account_mode, status, COUNT(*) AS n,
       COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(exits,'[]'::jsonb)) > 0) AS with_exits
FROM mi_live_trades GROUP BY 1,2 ORDER BY 1,2;

\echo ===Q1_LIVE_SHARE_MISMATCH===
WITH e AS (
  SELECT t.id, t.ticker, t.account_mode, t.alert_date, t.status, t.signal_type,
         t.entry_shares, t.remaining_shares, t.total_pnl, t.entry_attempt,
         t.partial_taken, t.entry_price,
         jsonb_array_length(COALESCE(t.exits,'[]'::jsonb)) AS n_exits,
         COALESCE((SELECT SUM((x->>'shares')::numeric)
                     FROM jsonb_array_elements(t.exits) x), 0) AS exit_shares
  FROM mi_live_trades t
  WHERE jsonb_array_length(COALESCE(t.exits,'[]'::jsonb)) > 0
)
SELECT *, (exit_shares + remaining_shares - entry_shares) AS over_by
FROM e
WHERE ABS(exit_shares + remaining_shares - entry_shares) > 0.001
ORDER BY alert_date;

\echo ===Q1B_CLOSED_ONLY_MISMATCH===
WITH e AS (
  SELECT t.id, t.ticker, t.account_mode, t.alert_date, t.status, t.entry_shares,
         t.remaining_shares, t.total_pnl, t.entry_attempt,
         COALESCE((SELECT SUM((x->>'shares')::numeric)
                     FROM jsonb_array_elements(t.exits) x), 0) AS exit_shares
  FROM mi_live_trades t
  WHERE t.status = 'closed'
    AND jsonb_array_length(COALESCE(t.exits,'[]'::jsonb)) > 0
)
SELECT *, (exit_shares - entry_shares) AS over_by
FROM e
WHERE ABS(exit_shares - entry_shares) > 0.001
ORDER BY alert_date;

\echo ===Q2_EXITS_OUT_OF_TIME_ORDER===
WITH legs AS (
  SELECT t.id, t.ticker, t.account_mode, t.alert_date, a.ord,
         (a.x->>'time') AS ts_raw,
         CASE WHEN a.x ? 'time' THEN (a.x->>'time')::timestamptz END AS ts
  FROM mi_live_trades t,
       LATERAL jsonb_array_elements(t.exits) WITH ORDINALITY AS a(x, ord)
  WHERE jsonb_array_length(COALESCE(t.exits,'[]'::jsonb)) > 1
), flagged AS (
  SELECT id, ticker, account_mode, alert_date, ord, ts,
         LAG(ts) OVER (PARTITION BY id ORDER BY ord) AS prev_ts
  FROM legs
)
SELECT id, ticker, account_mode, alert_date, ord, prev_ts, ts
FROM flagged
WHERE prev_ts IS NOT NULL AND ts IS NOT NULL AND ts < prev_ts
ORDER BY alert_date;

\echo ===Q2B_EXIT_LEGS_MISSING_TIME===
SELECT COUNT(*) AS legs_without_time
FROM mi_live_trades t, LATERAL jsonb_array_elements(t.exits) x
WHERE NOT (x ? 'time');

\echo ===Q3_ORDERS_FOR_MISMATCHED===
WITH bad AS (
  SELECT t.id
  FROM mi_live_trades t
  WHERE jsonb_array_length(COALESCE(t.exits,'[]'::jsonb)) > 0
    AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric)
                        FROM jsonb_array_elements(t.exits) x),0)
            + t.remaining_shares - t.entry_shares) > 0.001
)
SELECT o.trade_id, t.ticker, o.purpose, o.side, o.order_type, o.qty, o.filled_qty,
       o.filled_avg_price, o.status,
       to_char(o.created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS created_et
FROM mi_live_orders o
JOIN mi_live_trades t ON t.id = o.trade_id
WHERE o.trade_id IN (SELECT id FROM bad)
ORDER BY o.trade_id, o.created_at;

\echo ===Q4_EXIT_LEGS_FOR_MISMATCHED===
WITH bad AS (
  SELECT t.id
  FROM mi_live_trades t
  WHERE jsonb_array_length(COALESCE(t.exits,'[]'::jsonb)) > 0
    AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric)
                        FROM jsonb_array_elements(t.exits) x),0)
            + t.remaining_shares - t.entry_shares) > 0.001
)
SELECT t.id, t.ticker, t.account_mode, t.entry_shares, t.entry_price,
       t.total_pnl, t.exits::text
FROM mi_live_trades t WHERE t.id IN (SELECT id FROM bad) ORDER BY t.id;

\echo ===Q5_PAPER_TABLE_MISMATCH===
SELECT p.id, p.ticker, p.alert_date, p.status, p.remaining_shares, p.total_pnl,
       COALESCE((SELECT SUM((x->>'shares')::numeric) FROM jsonb_array_elements(p.entries) x),0) AS entry_shares,
       COALESCE((SELECT SUM((x->>'shares')::numeric) FROM jsonb_array_elements(p.exits) x),0) AS exit_shares
FROM mi_paper_trades p
WHERE jsonb_array_length(COALESCE(p.exits,'[]'::jsonb)) > 0
  AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric) FROM jsonb_array_elements(p.exits) x),0)
          + p.remaining_shares
          - COALESCE((SELECT SUM((x->>'shares')::numeric) FROM jsonb_array_elements(p.entries) x),0)) > 0.001
ORDER BY p.alert_date;

\echo ===Q5B_PAPER_TABLE_SIZE===
SELECT COUNT(*) AS n_rows,
       COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(exits,'[]'::jsonb)) > 0) AS with_exits
FROM mi_paper_trades;

\echo ===Q6_SHADOW_TABLE_MISMATCH===
SELECT COUNT(*) AS n_mismatch
FROM mi_orb_shadow_trades s
WHERE jsonb_array_length(COALESCE(s.exits,'[]'::jsonb)) > 0
  AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric) FROM jsonb_array_elements(s.exits) x),0)
          + COALESCE(s.remaining_shares,0) - COALESCE(s.entry_shares,0)) > 0.001;

\echo ===Q7_SELL_RECORDS_FOR_MISMATCHED===
WITH bad AS (
  SELECT t.id
  FROM mi_live_trades t
  WHERE jsonb_array_length(COALESCE(t.exits,'[]'::jsonb)) > 0
    AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric)
                        FROM jsonb_array_elements(t.exits) x),0)
            + t.remaining_shares - t.entry_shares) > 0.001
)
SELECT trade_id, ticker, account_mode, alert_date, entry_price, risk_per_share,
       entry_shares, realized_pnl, realized_r, partial_taken
FROM mi_sell_discipline_records
WHERE trade_id IN (SELECT id FROM bad) ORDER BY trade_id;

\echo ===Q8_R3_BLOCKED_ROWS===
SELECT to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS et,
       event_type, summary
FROM mi_audit_log
WHERE event_type IN ('r3_day1_reentry_blocked','reentry_blocked_gap_through','remaining_shares_clamped')
ORDER BY created_at;
