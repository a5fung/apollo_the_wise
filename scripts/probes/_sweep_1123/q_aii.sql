SET default_transaction_read_only = on;
SELECT 'live' src, id, status, entry_price, stop_price, shares, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') FROM mi_live_trades WHERE ticker='AII' AND created_at>='2026-11-11' AND created_at<'2026-11-12';
SELECT 'paper' src, id, status, entry_price, stop_price, shares, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') FROM mi_paper_trades WHERE ticker='AII' AND created_at>='2026-11-11' AND created_at<'2026-11-12';
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t, event_type, left(summary,220) FROM mi_audit_log WHERE created_at>='2026-11-11 09:32-05' AND created_at<'2026-11-11 16:30-05' AND (summary ILIKE '%AII%' OR detail::text ILIKE '%"AII"%') ORDER BY created_at LIMIT 40;
