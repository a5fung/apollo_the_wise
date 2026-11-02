SET default_transaction_read_only = on;
\echo == A. today's EP alerts
SELECT ticker, score_tier, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t FROM mi_ep_alerts WHERE alert_date = CURRENT_DATE ORDER BY created_at;
\echo == F. MTW / BWMN rows (stop leg, status)
SELECT id, ticker, status, entry_price, stop_price, hard_stop, entry_shares, remaining_shares, stop_order_id IS NOT NULL AS has_stop_leg, account_mode FROM mi_live_trades WHERE id IN (440, 451);
\echo == G. breakout_v1 events since 09:45 ET
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t, event_type, LEFT(summary,200) FROM mi_audit_log WHERE created_at >= (CURRENT_DATE::timestamp AT TIME ZONE 'America/New_York') + INTERVAL '9 hours 45 minutes' AND (event_type ILIKE 'breakout_v1%' OR summary ILIKE '%MTW%' OR summary ILIKE '%BWMN%') ORDER BY created_at;
\echo == H. any breakout order on the live account ever
SELECT COUNT(*) FROM mi_live_trades WHERE signal_type = 'breakout_v1' AND account_mode = 'live';
