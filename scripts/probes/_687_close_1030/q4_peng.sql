SET default_transaction_read_only = on;
SELECT id, ticker, status, remaining_shares, stop_price, (closed_at AT TIME ZONE 'America/New_York')::timestamp(0) closed_et, total_pnl FROM mi_live_trades WHERE id = 414;
SELECT (created_at AT TIME ZONE 'America/New_York')::timestamp(0) et, event_type, left(coalesce(summary,''),180) FROM mi_audit_log
WHERE created_at BETWEEN '2026-10-15 08:55-04' AND '2026-10-15 09:40-04' AND summary ILIKE '%PENG%' ORDER BY created_at LIMIT 12;
