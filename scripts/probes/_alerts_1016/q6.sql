-- READ-ONLY. Which ticker did the 10-16 carry-forward sector filter strip from the Residential theme?
SELECT created_at, left(detail, 600) FROM mi_audit_log WHERE event_type='theme_carryforward_filter_stripped'
  AND created_at BETWEEN '2026-10-16 21:00+00' AND '2026-10-16 21:13+00' AND summary ILIKE '%Residential Building%';
SELECT count(*) AS strips_30d FROM mi_audit_log WHERE event_type='theme_carryforward_filter_stripped' AND created_at >= now() - interval '30 days';
SELECT count(*) AS guard_flags_30d FROM mi_audit_log WHERE event_type='theme_member_pruned_while_rising' AND created_at >= now() - interval '30 days';
