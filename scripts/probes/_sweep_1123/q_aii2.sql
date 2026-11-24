SET default_transaction_read_only = on;
SELECT * FROM mi_live_trades WHERE ticker='AII' AND created_at>='2026-11-10' AND created_at<'2026-11-13';
SELECT * FROM mi_paper_trades WHERE ticker='AII' AND created_at>='2026-11-10' AND created_at<'2026-11-13';
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t, event_type, left(summary,200) FROM mi_audit_log WHERE created_at>='2026-11-11 09:32:00-05' AND created_at<'2026-11-11 09:33:30-05' ORDER BY created_at;
