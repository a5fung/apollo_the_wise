SET default_transaction_read_only = on;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t, event_type, left(summary,160) FROM mi_audit_log WHERE event_type='orb_bar_stream_used' AND created_at>='2026-10-30' ORDER BY created_at;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t, event_type, left(summary,200) FROM mi_audit_log WHERE created_at>='2026-10-30' AND summary ILIKE '%infra:no_bar%' ORDER BY created_at LIMIT 20;
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) FROM mi_audit_log WHERE event_type='orb_bar_fetched' AND created_at>='2026-10-30' AND detail::text ILIKE '%attempt%' GROUP BY 1 ORDER BY 1;
