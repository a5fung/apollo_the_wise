SET default_transaction_read_only = on;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t, left(summary,120), left(detail,500) FROM mi_audit_log WHERE event_type='theme_merge_adjudication_error' AND created_at > now() - interval '3 days' ORDER BY created_at;
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) FROM mi_audit_log WHERE event_type='theme_merge_adjudication_error' AND created_at > now() - interval '30 days' GROUP BY 1 ORDER BY 1;
