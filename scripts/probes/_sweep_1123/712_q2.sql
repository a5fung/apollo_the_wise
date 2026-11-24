SET default_transaction_read_only = on;
\d mi_intraday_bars
SELECT * FROM mi_intraday_bars WHERE ticker='AII' AND (ts AT TIME ZONE 'America/New_York')::date='2026-11-11' ORDER BY ts LIMIT 3;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t, event_type, left(summary,120) FROM mi_audit_log WHERE created_at>='2026-11-11 09:29-05' AND created_at<'2026-11-11 09:35-05' AND summary ILIKE '%AII%' ORDER BY created_at;
