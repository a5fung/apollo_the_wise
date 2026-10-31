SET default_transaction_read_only = on;
\echo == parent pass outcomes per night since 10-12
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_date, event_type, count(*) FROM mi_audit_log
WHERE event_type LIKE 'theme_parent_pass%' AND created_at >= '2026-10-12' GROUP BY 1,2 ORDER BY 1,2;
\echo == the distinct pairs, deduplicated across nights (child, candidate parent, the judge's reason)
SELECT detail, count(*) AS nights, min((created_at AT TIME ZONE 'America/New_York')::date) AS first_et, max((created_at AT TIME ZONE 'America/New_York')::date) AS last_et
FROM mi_audit_log WHERE event_type IN ('theme_parent_pass_distinct','theme_parent_pass_linked','theme_parent_pass_inverted') AND created_at >= '2026-10-12'
GROUP BY detail ORDER BY nights DESC, first_et;
