SET default_transaction_read_only = on;
SELECT to_char(bar_time AT TIME ZONE 'America/New_York','HH24:MI') t, open, high, low, close, volume FROM mi_intraday_bars WHERE ticker='AII' AND bar_time>='2026-11-11 09:30-05' AND bar_time<'2026-11-11 09:40-05' ORDER BY bar_time;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t, event_type, left(summary,160) FROM mi_audit_log WHERE created_at>='2026-11-11 09:32-05' AND created_at<'2026-11-11 10:30-05' AND summary ILIKE '%AII%' ORDER BY created_at LIMIT 25;
