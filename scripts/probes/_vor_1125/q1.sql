SET default_transaction_read_only = on;
SELECT * FROM mi_live_trades WHERE ticker='VOR' ORDER BY created_at DESC LIMIT 3;
SELECT created_at, event_type, summary, left(detail::text,600) FROM mi_audit_log WHERE (summary ILIKE '%VOR%' OR detail::text ILIKE '%"VOR"%') AND created_at > now()-interval '30 days' ORDER BY created_at;
