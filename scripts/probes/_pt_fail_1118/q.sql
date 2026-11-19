SET default_transaction_read_only = on;
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(detail::text, 1500) FROM mi_audit_log WHERE event_type LIKE 'profit_trigger%' AND created_at > now() - interval '3 days' ORDER BY created_at;
SELECT event_type, count(*), max(created_at AT TIME ZONE 'America/New_York') FROM mi_audit_log WHERE event_type LIKE 'profit_trigger%' GROUP BY 1;
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) FROM mi_audit_log WHERE event_type LIKE 'profit_trigger%' AND created_at > now() - interval '60 days' GROUP BY 1,2 ORDER BY 1 DESC LIMIT 20;
SELECT id, ticker, signal_type, account_mode, status, entry_price, entry_shares, partial_taken, highest_price_seen, filled_at AT TIME ZONE 'America/New_York' f, closed_at AT TIME ZONE 'America/New_York' c, exit_reason FROM mi_live_trades WHERE filled_at > now() - interval '2 days' ORDER BY filled_at;
