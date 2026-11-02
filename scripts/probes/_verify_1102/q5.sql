SET default_transaction_read_only = on;
SELECT id, ticker, status, skip_reason FROM mi_live_trades WHERE id = 451;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t, event_type, LEFT(summary,200) FROM mi_audit_log WHERE created_at >= NOW() - INTERVAL '3 hours' AND summary ILIKE '%BWMN%' ORDER BY created_at;
