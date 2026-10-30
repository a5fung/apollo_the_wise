SET default_transaction_read_only = on;
SELECT id, ticker, status, remaining_shares, stop_price, exit_reason, exit_price, total_pnl, (closed_at AT TIME ZONE 'America/New_York')::timestamp(0) closed_et, exits::text
FROM mi_live_trades WHERE id IN (429, 424);
SELECT (created_at AT TIME ZONE 'America/New_York')::timestamp(0) et, event_type, left(coalesce(summary,''),200)
FROM mi_audit_log WHERE created_at >= '2026-10-29 16:00-04' AND (summary ILIKE '%CLS%') ORDER BY created_at LIMIT 15;
