-- READ-ONLY. Any theme-run audit row naming the Residential theme on 10-16, and when IBP's 10-16 score row was written.
SELECT created_at, event_type, left(summary,240) FROM mi_audit_log
WHERE created_at BETWEEN '2026-10-16 20:55+00' AND '2026-10-16 21:40+00' AND (summary ILIKE '%Residential Building%' OR detail ILIKE '%Residential Building%') ORDER BY created_at;
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at BETWEEN '2026-10-16 21:00+00' AND '2026-10-16 21:13+00' GROUP BY 1 ORDER BY 2 DESC LIMIT 30;
