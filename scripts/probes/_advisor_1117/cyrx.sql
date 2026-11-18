SET default_transaction_read_only = on;
SELECT row_to_json(t) FROM mi_live_trades t WHERE id=786;
SELECT created_at AT TIME ZONE 'America/New_York', event_type, left(detail::text,700) FROM mi_audit_log WHERE event_type IN ('breakout_v1_entry_order','orb_cancellation_reclassified') AND summary LIKE 'CYRX%' AND created_at > NOW() - INTERVAL '14 hours';
