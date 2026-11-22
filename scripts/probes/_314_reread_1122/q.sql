SET default_transaction_read_only = on;
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type, left(detail::text,160)
FROM mi_audit_log WHERE event_type = 'parabolic_short_shadow_run' AND created_at >= '2026-11-14' ORDER BY 1;
SELECT scan_date, stage, count(*) FROM mi_parabolic_candidates WHERE scan_date >= '2026-11-14' GROUP BY 1,2 ORDER BY 1,2;
SELECT count(*) AS shadow_rows FROM mi_parabolic_short_shadow;
