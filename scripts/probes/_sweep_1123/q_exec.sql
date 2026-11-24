SET default_transaction_read_only = on;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24') hr, count(*) FROM api_usage WHERE caller='theme_merge_adjudication' AND created_at > now()-interval '30 days' GROUP BY 1 ORDER BY 1;
SELECT to_char(t.created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t, t.* FROM trades t WHERE ticker='AII' AND (created_at AT TIME ZONE 'America/New_York')::date='2026-11-11';
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t, event_type, left(summary,200) FROM mi_audit_log WHERE created_at>='2026-11-11 09:32-05' AND created_at<'2026-11-11 16:00-05' AND (summary ILIKE '%AII%' OR details::text ILIKE '%"AII"%') ORDER BY created_at LIMIT 40;
