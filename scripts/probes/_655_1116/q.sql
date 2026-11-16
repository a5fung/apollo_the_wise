SET default_transaction_read_only = on;
\echo == Q1 operator promotions since 10-10
SELECT id, (created_at AT TIME ZONE 'America/New_York')::timestamp(0) AS et, summary FROM mi_audit_log WHERE event_type='theme_operator_promoted' AND created_at >= '2026-10-10' ORDER BY created_at;
\echo == Q2 exempt / exempt_error rows since 10-17
SELECT id, event_type, (created_at AT TIME ZONE 'America/New_York')::timestamp(0) AS et, left(summary,300) FROM mi_audit_log WHERE event_type IN ('theme_pass1_5_operator_exempt','theme_pass1_5_operator_exempt_error') AND created_at >= '2026-10-17' ORDER BY created_at;
\echo == Q3 pass1.5 absorption rows since 10-17 full (is a promoted theme on the LEFT inside its 3-night window?)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::timestamp(0) AS et, left(summary,400) FROM mi_audit_log WHERE event_type='theme_pass1_5_absorption' AND created_at >= '2026-10-17' ORDER BY created_at;
\echo == Q4 engine nights since 10-17
SELECT theme_date, count(*) FROM mi_themes WHERE source='live' AND theme_date >= '2026-10-17' GROUP BY 1 ORDER BY 1;
